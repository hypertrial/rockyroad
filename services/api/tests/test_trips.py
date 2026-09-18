from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from rockyroad_api.db import Database
from rockyroad_api.models import (
    Maneuver,
    RouteAlternative,
    SavedPlaceIn,
    StopIn,
    StopOut,
    TripCreate,
    TripSettingsIn,
    TripSettingsOut,
    TripUpdate,
)
from rockyroad_api.routing import RouteComputation, RoutingError
from rockyroad_api.trips import (
    apply_optimized_order,
    create_saved_place,
    create_trip,
    delete_trip,
    get_trip,
    list_saved_places,
    list_trips,
    replace_stops,
    route_trip,
    update_trip,
)

CALGARY = StopIn(name="Calgary", lon=-114.07, lat=51.05)

CHARLOTTETOWN = StopIn(name="Charlottetown", lon=-63.131, lat=46.238)
SUMMERSIDE = StopIn(name="Summerside", lon=-63.79, lat=46.393)


def test_create_and_list_trips(db: Database) -> None:
    created = create_trip(db, TripCreate(name="Island loop", stops=[CHARLOTTETOWN]))
    assert created.name == "Island loop"
    assert created.stops[0].position == 0
    summaries = list_trips(db)
    assert summaries[0].id == created.id
    assert summaries[0].stop_count == 1


def test_apply_optimized_order_permutes_and_rejects_invalid(db: Database) -> None:
    trip = create_trip(db, TripCreate(name="Order", stops=[CHARLOTTETOWN, SUMMERSIDE]))
    first, second = trip.stops
    reordered = apply_optimized_order(trip.stops, [1, 0])
    assert [stop.id for stop in reordered] == [second.id, first.id]
    assert [stop.position for stop in reordered] == [0, 1]
    assert apply_optimized_order(trip.stops, [0, 2]) == trip.stops


def test_apply_optimized_order_preserves_region(db: Database) -> None:
    trip = create_trip(
        db,
        TripCreate(
            name="Labeled",
            stops=[
                StopIn(name="Vancouver", lon=-123.12, lat=49.26, region="British Columbia, Canada"),
                StopIn(name="Calgary", lon=-114.07, lat=51.05, region="Alberta, Canada"),
            ],
        ),
    )
    reordered = apply_optimized_order(trip.stops, [1, 0])
    assert [stop.name for stop in reordered] == ["Calgary", "Vancouver"]
    assert [stop.region for stop in reordered] == ["Alberta, Canada", "British Columbia, Canada"]


def test_stop_order_is_stable(db: Database) -> None:
    trip = create_trip(db, TripCreate(name="Order", stops=[CHARLOTTETOWN, SUMMERSIDE]))
    updated = replace_stops(db, trip.id, [SUMMERSIDE, CHARLOTTETOWN])
    assert updated is not None
    assert [stop.name for stop in updated.stops] == ["Summerside", "Charlottetown"]
    assert [stop.position for stop in updated.stops] == [0, 1]


def test_rejects_overseas_coordinates(db: Database) -> None:
    try:
        create_trip(
            db,
            TripCreate(name="Paris", stops=[StopIn(name="Paris", lon=2.35, lat=48.85)]),
        )
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_create_trip_rejects_stops_outside_sample_extract(db: Database) -> None:
    (db.settings.osm_dir / "manifest.json").write_text(json.dumps({"profile": "sample"}), encoding="utf-8")
    with pytest.raises(ValueError, match="Prince Edward Island"):
        create_trip(db, TripCreate(name="Prairie", stops=[CALGARY]))


def test_hosted_create_trip_allows_continental_stops(db: Database) -> None:
    db.settings = db.settings.model_copy(update={"provider_mode": "hosted"})
    trip = create_trip(db, TripCreate(name="Prairie", stops=[CALGARY, CHARLOTTETOWN]))
    assert [stop.name for stop in trip.stops] == ["Calgary", "Charlottetown"]


def test_hosted_create_trip_rejects_outside_canada_usa(db: Database) -> None:
    db.settings = db.settings.model_copy(update={"provider_mode": "hosted"})
    hawaii = StopIn(name="Honolulu", lon=-157.86, lat=21.31)
    with pytest.raises(ValueError, match="Canada and the USA") as exc:
        create_trip(db, TripCreate(name="Pacific", stops=[hawaii]))
    assert "Prince Edward Island" not in str(exc.value)


def test_create_trip_outside_canada_usa_does_not_mention_pei(db: Database) -> None:
    (db.settings.osm_dir / "manifest.json").write_text(json.dumps({"profile": "canada-usa"}), encoding="utf-8")
    hawaii = StopIn(name="Honolulu", lon=-157.86, lat=21.31)
    with pytest.raises(ValueError, match="canada-usa") as exc:
        create_trip(db, TripCreate(name="Pacific", stops=[hawaii]))
    assert "Prince Edward Island" not in str(exc.value)


def test_replace_stops_allows_outside_extract_so_pins_can_be_removed(db: Database) -> None:
    (db.settings.osm_dir / "manifest.json").write_text(json.dumps({"profile": "sample"}), encoding="utf-8")
    trip = create_trip(db, TripCreate(name="Cleanup", stops=[CHARLOTTETOWN, SUMMERSIDE]))
    updated = replace_stops(db, trip.id, [CALGARY, CHARLOTTETOWN])
    assert updated is not None
    assert [stop.name for stop in updated.stops] == ["Calgary", "Charlottetown"]
    cleared = replace_stops(db, trip.id, [CHARLOTTETOWN])
    assert cleared is not None
    assert [stop.name for stop in cleared.stops] == ["Charlottetown"]


def test_route_trip_rejects_stops_outside_sample_extract(db: Database) -> None:
    (db.settings.osm_dir / "manifest.json").write_text(json.dumps({"profile": "sample"}), encoding="utf-8")
    trip = create_trip(db, TripCreate(name="Prairie"))
    replace_stops(db, trip.id, [CALGARY, StopIn(name="Edmonton", lon=-113.49, lat=53.54)])
    with pytest.raises(RoutingError, match="Prince Edward Island") as exc:
        route_trip(db, client=None, trip_id=trip.id)  # type: ignore[arg-type]
    assert exc.value.status_code == 422


def test_settings_and_delete(db: Database) -> None:
    trip = create_trip(db, TripCreate(name="Settings"))
    updated = update_trip(
        db,
        trip.id,
        TripUpdate(name="Renamed", settings=TripSettingsIn(avoid_tolls=True, avoid_ferries=True)),
    )
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.settings.avoid_tolls is True
    assert delete_trip(db, trip.id) is True
    assert list_trips(db) == []


def test_route_rejects_stale_optimized_result_without_overwriting_stops(db: Database) -> None:
    trip = create_trip(
        db,
        TripCreate(
            name="Race",
            stops=[CHARLOTTETOWN, SUMMERSIDE, StopIn(name="Cavendish", lon=-63.45, lat=46.49)],
            settings=TripSettingsIn(optimize=True),
        ),
    )
    started = threading.Event()
    release = threading.Event()
    alternative = RouteAlternative(
        index=0,
        distance_m=1_000,
        duration_s=100,
        geometry={"type": "LineString", "coordinates": [[-63.13, 46.24], [-63.79, 46.39]]},
        maneuvers=[Maneuver(instruction="Go", distance_m=1_000, duration_s=100)],
    )

    class BlockingProvider:
        def request_route(self, stops: list[StopOut], settings: TripSettingsOut) -> RouteComputation:
            assert stops and settings.optimize
            started.set()
            assert release.wait(timeout=5)
            return RouteComputation(alternatives=[alternative], optimized_order=[0, 2, 1])

    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(route_trip, db, BlockingProvider(), trip.id)
        assert started.wait(timeout=5)
        replacement = StopIn(id=uuid4(), name="New stop", lon=-63.3, lat=46.3)
        updated = replace_stops(db, trip.id, [CHARLOTTETOWN, replacement, SUMMERSIDE])
        assert updated is not None
        release.set()
        with pytest.raises(RoutingError, match="trip changed") as exc:
            future.result(timeout=5)

    assert exc.value.status_code == 409
    current = get_trip(db, trip.id)
    assert current is not None
    assert [stop.name for stop in current.stops] == ["Charlottetown", "New stop", "Summerside"]


def test_replace_stops_rejects_duplicate_ids_before_writing(db: Database) -> None:
    trip = create_trip(db, TripCreate(name="Duplicates", stops=[CHARLOTTETOWN, SUMMERSIDE]))
    duplicate = uuid4()
    with pytest.raises(ValueError, match="unique"):
        replace_stops(
            db,
            trip.id,
            [
                StopIn(id=duplicate, name="A", lon=-63.13, lat=46.24),
                StopIn(id=duplicate, name="B", lon=-63.79, lat=46.39),
            ],
        )
    current = get_trip(db, trip.id)
    assert current is not None
    assert [stop.name for stop in current.stops] == ["Charlottetown", "Summerside"]


def test_replace_stops_rejects_id_owned_by_another_trip_before_writing(db: Database) -> None:
    first = create_trip(db, TripCreate(name="First", stops=[CHARLOTTETOWN]))
    second = create_trip(db, TripCreate(name="Second", stops=[SUMMERSIDE]))

    with pytest.raises(ValueError, match="another trip"):
        replace_stops(
            db,
            second.id,
            [StopIn(id=first.stops[0].id, name="Stolen", lon=-63.5, lat=46.3)],
        )

    current_first = get_trip(db, first.id)
    current_second = get_trip(db, second.id)
    assert current_first is not None and [stop.name for stop in current_first.stops] == ["Charlottetown"]
    assert current_second is not None and [stop.name for stop in current_second.stops] == ["Summerside"]


def test_stop_region_round_trips_and_defaults_to_null(db: Database) -> None:
    vancouver = StopIn(
        name="Vancouver",
        lon=-123.12,
        lat=49.26,
        place_id="photon:N:1",
        region="British Columbia, Canada",
    )
    created = create_trip(db, TripCreate(name="Coast", stops=[vancouver, CHARLOTTETOWN]))
    assert created.stops[0].region == "British Columbia, Canada"
    assert created.stops[1].region is None
    updated = replace_stops(
        db,
        created.id,
        [
            StopIn(id=created.stops[0].id, name="Vancouver", lon=-123.12, lat=49.26, region="British Columbia, Canada"),
            StopIn(name="Map pin", lon=-63.2, lat=46.3),
        ],
    )
    assert updated is not None
    assert updated.stops[0].region == "British Columbia, Canada"
    assert updated.stops[1].region is None


def test_stop_region_rejects_overlong_values() -> None:
    with pytest.raises(ValueError):
        StopIn(name="Vancouver", lon=-123.12, lat=49.26, region="x" * 201)
    assert StopIn(name="Vancouver", lon=-123.12, lat=49.26, region="x" * 200).region == "x" * 200


def test_stop_region_can_be_cleared_on_replace(db: Database) -> None:
    created = create_trip(
        db,
        TripCreate(
            name="Coast",
            stops=[StopIn(name="Vancouver", lon=-123.12, lat=49.26, region="British Columbia, Canada")],
        ),
    )
    updated = replace_stops(
        db,
        created.id,
        [StopIn(id=created.stops[0].id, name="Vancouver", lon=-123.12, lat=49.26, region=None)],
    )
    assert updated is not None
    assert updated.stops[0].region is None


def test_saved_place_region_round_trips(db: Database) -> None:
    saved = create_saved_place(
        db,
        SavedPlaceIn(
            name="Vancouver",
            lon=-123.12,
            lat=49.26,
            place_id="photon:N:1",
            region="British Columbia, Canada",
        ),
    )
    assert saved.region == "British Columbia, Canada"
    listed = list_saved_places(db)
    assert listed[0].id == saved.id
    assert listed[0].region == "British Columbia, Canada"
    unlabeled = create_saved_place(db, SavedPlaceIn(name="Map pin", lon=-63.13, lat=46.24))
    assert unlabeled.region is None


def test_saved_place_region_rejects_overlong_values() -> None:
    with pytest.raises(ValueError):
        SavedPlaceIn(name="Vancouver", lon=-123.12, lat=49.26, region="x" * 201)
