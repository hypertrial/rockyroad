from __future__ import annotations

import json

import pytest

from rockyroad_api.db import Database
from rockyroad_api.models import StopIn, TripCreate, TripSettingsIn, TripUpdate
from rockyroad_api.routing import RoutingError
from rockyroad_api.trips import (
    apply_optimized_order,
    create_trip,
    delete_trip,
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
