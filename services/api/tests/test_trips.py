from __future__ import annotations

from rockyroad_api.db import Database
from rockyroad_api.models import StopIn, TripCreate, TripSettingsIn, TripUpdate
from rockyroad_api.trips import apply_optimized_order, create_trip, delete_trip, list_trips, replace_stops, update_trip

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
