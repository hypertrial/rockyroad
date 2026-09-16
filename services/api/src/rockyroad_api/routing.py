from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any
from uuid import UUID

import httpx

from rockyroad_api.models import (
    Maneuver,
    RouteAlternative,
    RouteResponse,
    StopOut,
    TripSettingsOut,
)
from rockyroad_api.polyline import decode_polyline
from rockyroad_api.settings import Settings
from rockyroad_data.manifests import read_json
from rockyroad_data.paths import ROUTING_MANIFEST


class RoutingError(RuntimeError):
    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


def routing_data_version(settings: Settings) -> str:
    manifest = read_json(settings.routing_dir / "manifest.json")
    if not manifest:
        manifest = read_json(ROUTING_MANIFEST)
    return str(manifest.get("version") or "unknown")


def cache_key(
    stops: list[StopOut],
    settings: TripSettingsOut,
    data_version: str,
) -> str:
    payload = {
        "stops": [(stop.lon, stop.lat, stop.position) for stop in sorted(stops, key=lambda item: item.position)],
        "avoid_tolls": settings.avoid_tolls,
        "avoid_highways": settings.avoid_highways,
        "avoid_ferries": settings.avoid_ferries,
        "costing": settings.costing,
        "optimize": settings.optimize,
        "data_version": data_version,
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def valhalla_payload(stops: list[StopOut], settings: TripSettingsOut, *, optimized: bool) -> dict[str, Any]:
    costing_options = {
        settings.costing: {
            "use_highways": 0.0 if settings.avoid_highways else 1.0,
            "use_tolls": 0.0 if settings.avoid_tolls else 1.0,
            "use_ferry": 0.0 if settings.avoid_ferries else 1.0,
        }
    }
    body: dict[str, Any] = {
        "locations": [{"lat": stop.lat, "lon": stop.lon, "name": stop.name} for stop in stops],
        "costing": settings.costing,
        "costing_options": costing_options,
        "directions_options": {"units": "kilometers"},
        "id": "rockyroad",
    }
    if not optimized:
        body["alternates"] = 2
    return body


def _maneuvers_from_legs(trip: dict[str, Any]) -> list[Maneuver]:
    maneuvers: list[Maneuver] = []
    for leg in trip.get("legs") or []:
        for item in leg.get("maneuvers") or []:
            maneuvers.append(
                Maneuver(
                    instruction=str(item.get("instruction") or item.get("verbal_pre_transition_instruction") or ""),
                    type=item.get("type"),
                    distance_m=float(item.get("length") or 0.0) * 1000.0,
                    duration_s=float(item.get("time") or 0.0),
                    begin_shape_index=int(item.get("begin_shape_index") or 0),
                )
            )
    return maneuvers


def parse_valhalla(payload: dict[str, Any]) -> list[RouteAlternative]:
    trips: list[dict[str, Any]] = []
    if "trip" in payload:
        trips.append(payload["trip"])
    trips.extend(payload.get("alternates") or [])
    alternatives: list[RouteAlternative] = []
    for index, trip in enumerate(trips):
        if "trip" in trip and "legs" not in trip:
            trip = trip["trip"]
        summary = trip.get("summary") or {}
        shape = trip.get("shape") or ""
        geometry = {"type": "LineString", "coordinates": decode_polyline(shape) if shape else []}
        alternatives.append(
            RouteAlternative(
                index=index,
                distance_m=float(summary.get("length") or 0.0) * 1000.0,
                duration_s=float(summary.get("time") or 0.0),
                geometry=geometry,
                maneuvers=_maneuvers_from_legs(trip),
            )
        )
    return alternatives


class ValhallaClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.valhalla_timeout_s)

    def request_route(self, stops: list[StopOut], settings: TripSettingsOut) -> list[RouteAlternative]:
        if len(stops) < 2:
            raise RoutingError("at least two stops are required to build a route", status_code=400)
        path = "/optimized_route" if settings.optimize else "/route"
        body = valhalla_payload(stops, settings, optimized=settings.optimize)
        try:
            response = self.client.post(f"{self.settings.valhalla_url.rstrip('/')}{path}", json=body)
        except httpx.HTTPError as exc:
            raise RoutingError("Valhalla routing service is unavailable") from exc
        if response.status_code >= 400:
            detail = response.text[:300]
            raise RoutingError(
                f"routing data could not produce a path ({response.status_code}): {detail}",
                status_code=422 if response.status_code < 500 else 503,
            )
        return parse_valhalla(response.json())


def persist_route(
    conn: Any,
    trip_id: UUID,
    key: str,
    data_version: str,
    alternatives: list[RouteAlternative],
) -> None:
    conn.execute("DELETE FROM route_legs WHERE trip_id = ?", [str(trip_id)])
    for alternative in alternatives:
        conn.execute(
            """
            INSERT INTO route_legs
            VALUES (?, ?, ?, ?, ?, ?::JSON, ?, ?, ?::JSON, now())
            """,
            [
                str(uuid.uuid4()),
                str(trip_id),
                key,
                data_version,
                alternative.index,
                json.dumps(alternative.geometry),
                alternative.distance_m,
                alternative.duration_s,
                json.dumps([item.model_dump() for item in alternative.maneuvers]),
            ],
        )


def load_cached_route(conn: Any, trip_id: UUID, key: str) -> list[RouteAlternative]:
    rows = conn.execute(
        """
        SELECT alternative_index, geometry, distance_m, duration_s, maneuvers
        FROM route_legs
        WHERE trip_id = ? AND cache_key = ?
        ORDER BY alternative_index
        """,
        [str(trip_id), key],
    ).fetchall()
    alternatives: list[RouteAlternative] = []
    for row in rows:
        geometry = row[1] if isinstance(row[1], dict) else json.loads(row[1])
        maneuvers_raw = row[4] if isinstance(row[4], list) else json.loads(row[4])
        alternatives.append(
            RouteAlternative(
                index=int(row[0]),
                distance_m=float(row[2]),
                duration_s=float(row[3]),
                geometry=geometry,
                maneuvers=[Maneuver.model_validate(item) for item in maneuvers_raw],
            )
        )
    return alternatives


def to_route_response(
    trip_id: UUID,
    alternatives: list[RouteAlternative],
    *,
    cache_hit: bool,
    data_version: str,
) -> RouteResponse:
    return RouteResponse(
        trip_id=trip_id,
        cache_hit=cache_hit,
        data_version=data_version,
        alternatives=alternatives,
    )
