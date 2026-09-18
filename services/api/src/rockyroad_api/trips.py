from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from rockyroad_api.db import Database
from rockyroad_api.geo import (
    extract_bounds,
    extract_coverage_hint,
    extract_profile,
    hosted_bounds,
    point_in_extract,
)
from rockyroad_api.models import (
    RouteResponse,
    SavedPlaceIn,
    SavedPlaceOut,
    StopIn,
    StopOut,
    TripCreate,
    TripOut,
    TripSettingsIn,
    TripSettingsOut,
    TripSummary,
    TripUpdate,
)
from rockyroad_api.ors import MAX_ORS_STOPS
from rockyroad_api.providers import RouteProvider
from rockyroad_api.routing import (
    RouteComputation,
    RoutingError,
    cache_key,
    load_cached_route,
    persist_route,
    routing_data_version,
    to_route_response,
)


def _row_stop(row: tuple[Any, ...]) -> StopOut:
    return StopOut(
        id=row[0],
        trip_id=row[1],
        position=row[2],
        name=row[3],
        lon=row[4],
        lat=row[5],
        place_id=row[6],
        created_at=row[7],
    )


def _row_settings(row: tuple[Any, ...]) -> TripSettingsOut:
    return TripSettingsOut(
        trip_id=row[0],
        avoid_tolls=bool(row[1]),
        avoid_highways=bool(row[2]),
        avoid_ferries=bool(row[3]),
        costing=row[4],
        optimize=bool(row[5]),
        selected_alternative=int(row[6]),
        updated_at=row[7],
    )


def list_trips(db: Database) -> list[TripSummary]:
    rows = db.conn.execute(
        """
        SELECT t.id, t.name, t.created_at, t.updated_at, COUNT(s.id)
        FROM trips t
        LEFT JOIN trip_stops s ON s.trip_id = t.id
        GROUP BY t.id, t.name, t.created_at, t.updated_at
        ORDER BY t.updated_at DESC
        """
    ).fetchall()
    return [
        TripSummary(id=row[0], name=row[1], created_at=row[2], updated_at=row[3], stop_count=int(row[4]))
        for row in rows
    ]


def apply_optimized_order(stops: list[StopOut], order: list[int]) -> list[StopOut]:
    if len(order) != len(stops) or sorted(order) != list(range(len(stops))):
        return list(stops)
    return [stops[index].model_copy(update={"position": position}) for position, index in enumerate(order)]


def _as_stop_in(stops: list[StopOut]) -> list[StopIn]:
    return [StopIn(id=stop.id, name=stop.name, lon=stop.lon, lat=stop.lat, place_id=stop.place_id) for stop in stops]


def _routing_revision(trip: TripOut) -> tuple[object, ...]:
    return (
        tuple((stop.id, stop.name, stop.lon, stop.lat, stop.place_id) for stop in trip.stops),
        trip.settings.avoid_tolls,
        trip.settings.avoid_highways,
        trip.settings.avoid_ferries,
        trip.settings.costing,
        trip.settings.optimize,
        trip.settings.selected_alternative,
    )


def get_trip(db: Database, trip_id: UUID) -> TripOut | None:
    version = routing_data_version(db.settings)

    def _read(conn: Any) -> TripOut | None:
        trip = conn.execute(
            "SELECT id, name, created_at, updated_at FROM trips WHERE id = ?",
            [str(trip_id)],
        ).fetchone()
        if trip is None:
            return None
        stops = [
            _row_stop(row)
            for row in conn.execute(
                """
                SELECT id, trip_id, position, name, lon, lat, place_id, created_at
                FROM trip_stops
                WHERE trip_id = ?
                ORDER BY position
                """,
                [str(trip_id)],
            ).fetchall()
        ]
        settings_row = conn.execute(
            """
            SELECT trip_id, avoid_tolls, avoid_highways, avoid_ferries, costing, optimize,
                   selected_alternative, updated_at
            FROM trip_settings
            WHERE trip_id = ?
            """,
            [str(trip_id)],
        ).fetchone()
        if settings_row is None:
            return None
        settings = _row_settings(settings_row)
        alternatives = load_cached_route(conn, trip_id, cache_key(stops, settings, version))
        route = to_route_response(trip_id, alternatives, cache_hit=True, data_version=version) if alternatives else None
        return TripOut(
            id=trip[0],
            name=trip[1],
            created_at=trip[2],
            updated_at=trip[3],
            stops=stops,
            settings=settings,
            route=route,
        )

    return db.read(_read)


def _validate_stops(db: Database, stops: list[StopIn], *, for_route: bool = False) -> None:
    if db.settings.hosted:
        hint = extract_coverage_hint(None, hosted=True)
        bounds = hosted_bounds()
        if for_route and len(stops) > MAX_ORS_STOPS:
            raise ValueError(f"OpenRouteService accepts at most {MAX_ORS_STOPS} stops.")
        for stop in stops:
            stop.validate_location()
            if not point_in_extract(stop.lon, stop.lat, bounds):
                raise ValueError(f"{stop.name} is outside Canada and the USA coverage. {hint}")
        return
    bounds = extract_bounds(db.settings.osm_dir)
    hint = extract_coverage_hint(extract_profile(db.settings.osm_dir))
    for stop in stops:
        stop.validate_location()
        if not point_in_extract(stop.lon, stop.lat, bounds):
            raise ValueError(f"{stop.name} is outside the local OSM extract. {hint}")


def create_trip(db: Database, payload: TripCreate) -> TripOut:
    _validate_stops(db, payload.stops)
    trip_id = uuid.uuid4()

    def _write(conn: Any) -> None:
        conn.execute(
            "INSERT INTO trips VALUES (?, ?, now(), now())",
            [str(trip_id), payload.name],
        )
        _replace_stops(conn, trip_id, payload.stops)
        _upsert_settings(conn, trip_id, payload.settings)

    db.write(_write)
    trip = get_trip(db, trip_id)
    assert trip is not None
    return trip


def update_trip(db: Database, trip_id: UUID, payload: TripUpdate) -> TripOut | None:
    existing = get_trip(db, trip_id)
    if existing is None:
        return None

    def _write(conn: Any) -> None:
        if payload.name is not None:
            conn.execute(
                "UPDATE trips SET name = ?, updated_at = now() WHERE id = ?",
                [payload.name, str(trip_id)],
            )
        if payload.settings is not None:
            _upsert_settings(conn, trip_id, payload.settings)
            conn.execute("UPDATE trips SET updated_at = now() WHERE id = ?", [str(trip_id)])

    db.write(_write)
    return get_trip(db, trip_id)


def replace_stops(db: Database, trip_id: UUID, stops: list[StopIn]) -> TripOut | None:
    if get_trip(db, trip_id) is None:
        return None
    for stop in stops:
        stop.validate_location()

    def _write(conn: Any) -> None:
        _replace_stops(conn, trip_id, stops)
        conn.execute("DELETE FROM route_legs WHERE trip_id = ?", [str(trip_id)])
        conn.execute("UPDATE trips SET updated_at = now() WHERE id = ?", [str(trip_id)])

    db.write(_write)
    return get_trip(db, trip_id)


def delete_trip(db: Database, trip_id: UUID) -> bool:
    if get_trip(db, trip_id) is None:
        return False

    def _write(conn: Any) -> None:
        conn.execute("DELETE FROM route_legs WHERE trip_id = ?", [str(trip_id)])
        conn.execute("DELETE FROM trip_stops WHERE trip_id = ?", [str(trip_id)])
        conn.execute("DELETE FROM trip_settings WHERE trip_id = ?", [str(trip_id)])
        conn.execute("DELETE FROM trips WHERE id = ?", [str(trip_id)])

    db.write(_write)
    return True


def route_trip(db: Database, client: RouteProvider, trip_id: UUID, *, force_optimize: bool = False) -> RouteResponse:
    trip = get_trip(db, trip_id)
    if trip is None:
        raise RoutingError("trip not found", status_code=404)
    if len(trip.stops) < 2:
        raise RoutingError("at least two stops are required to build a route", status_code=400)
    try:
        _validate_stops(db, _as_stop_in(trip.stops), for_route=True)
    except ValueError as exc:
        raise RoutingError(str(exc), status_code=422) from exc
    version = routing_data_version(db.settings)
    original_revision = _routing_revision(trip)
    settings = trip.settings.model_copy(update={"optimize": True}) if force_optimize else trip.settings
    key = cache_key(trip.stops, settings, version)
    cached = db.read(lambda conn: load_cached_route(conn, trip_id, key))
    if cached and not force_optimize:
        return to_route_response(trip_id, cached, cache_hit=True, data_version=version)
    computation = RouteComputation(alternatives=cached) if cached else client.request_route(trip.stops, settings)
    ordered_stops = trip.stops
    if settings.optimize and computation.optimized_order is not None:
        ordered_stops = apply_optimized_order(trip.stops, computation.optimized_order)
    persist_key = cache_key(ordered_stops, settings, version)
    reordered = [stop.id for stop in ordered_stops] != [stop.id for stop in trip.stops]

    def _write(conn: Any) -> None:
        current = get_trip(db, trip_id)
        if current is None:
            raise RoutingError("trip not found", status_code=404)
        if _routing_revision(current) != original_revision:
            raise RoutingError("trip changed while the route was being built; try again", status_code=409)
        if force_optimize:
            _upsert_settings(conn, trip_id, settings)
        if reordered:
            _replace_stops(conn, trip_id, _as_stop_in(ordered_stops))
        if not cached:
            persist_route(conn, trip_id, persist_key, version, computation.alternatives)
        conn.execute("UPDATE trips SET updated_at = now() WHERE id = ?", [str(trip_id)])

    db.write(_write)
    return to_route_response(trip_id, computation.alternatives, cache_hit=bool(cached), data_version=version)


def optimize_trip(db: Database, client: RouteProvider, trip_id: UUID) -> RouteResponse:
    return route_trip(db, client, trip_id, force_optimize=True)


def list_saved_places(db: Database) -> list[SavedPlaceOut]:
    rows = db.conn.execute(
        """
        SELECT id, name, lon, lat, place_id, notes, created_at
        FROM saved_places
        ORDER BY created_at DESC
        """
    ).fetchall()
    return [
        SavedPlaceOut(
            id=row[0],
            name=row[1],
            lon=row[2],
            lat=row[3],
            place_id=row[4],
            notes=row[5],
            created_at=row[6],
        )
        for row in rows
    ]


def create_saved_place(db: Database, payload: SavedPlaceIn) -> SavedPlaceOut:
    payload.validate_location()
    place_id = uuid.uuid4()

    def _write(conn: Any) -> None:
        conn.execute(
            "INSERT INTO saved_places VALUES (?, ?, ?, ?, ?, ?, now())",
            [str(place_id), payload.name, payload.lon, payload.lat, payload.place_id, payload.notes],
        )

    db.write(_write)
    row = db.conn.execute(
        "SELECT id, name, lon, lat, place_id, notes, created_at FROM saved_places WHERE id = ?",
        [str(place_id)],
    ).fetchone()
    assert row is not None
    return SavedPlaceOut(
        id=row[0],
        name=row[1],
        lon=row[2],
        lat=row[3],
        place_id=row[4],
        notes=row[5],
        created_at=row[6],
    )


def delete_saved_place(db: Database, place_id: UUID) -> bool:
    existing = db.conn.execute("SELECT id FROM saved_places WHERE id = ?", [str(place_id)]).fetchone()
    if existing is None:
        return False

    def _write(conn: Any) -> None:
        conn.execute("DELETE FROM saved_places WHERE id = ?", [str(place_id)])

    db.write(_write)
    return True


def _replace_stops(conn: Any, trip_id: UUID, stops: list[StopIn]) -> None:
    stop_ids = [stop.id for stop in stops if stop.id is not None]
    if len(stop_ids) != len(set(stop_ids)):
        raise ValueError("stop ids must be unique")
    for stop_id in stop_ids:
        owner = conn.execute("SELECT trip_id FROM trip_stops WHERE id = ?", [str(stop_id)]).fetchone()
        if owner is not None and str(owner[0]) != str(trip_id):
            raise ValueError("stop id belongs to another trip")
    conn.execute("DELETE FROM trip_stops WHERE trip_id = ?", [str(trip_id)])
    for index, stop in enumerate(stops):
        conn.execute(
            "INSERT INTO trip_stops VALUES (?, ?, ?, ?, ?, ?, ?, now())",
            [
                str(stop.id or uuid.uuid4()),
                str(trip_id),
                index,
                stop.name,
                stop.lon,
                stop.lat,
                stop.place_id,
            ],
        )


def _upsert_settings(conn: Any, trip_id: UUID, settings: TripSettingsIn) -> None:
    conn.execute(
        """
        INSERT INTO trip_settings
        VALUES (?, ?, ?, ?, ?, ?, ?, now())
        ON CONFLICT (trip_id) DO UPDATE SET
            avoid_tolls = excluded.avoid_tolls,
            avoid_highways = excluded.avoid_highways,
            avoid_ferries = excluded.avoid_ferries,
            costing = excluded.costing,
            optimize = excluded.optimize,
            selected_alternative = excluded.selected_alternative,
            updated_at = now()
        """,
        [
            str(trip_id),
            settings.avoid_tolls,
            settings.avoid_highways,
            settings.avoid_ferries,
            settings.costing,
            settings.optimize,
            settings.selected_alternative,
        ],
    )
