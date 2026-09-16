from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from rockyroad_api.models import StopOut, TripSettingsOut
from rockyroad_api.polyline import decode_polyline
from rockyroad_api.routing import cache_key, parse_optimized_order, parse_valhalla, valhalla_payload


def _stop(name: str, lon: float, lat: float, position: int) -> StopOut:
    now = datetime.now()
    trip_id = uuid4()
    return StopOut(
        id=uuid4(),
        trip_id=trip_id,
        position=position,
        name=name,
        lon=lon,
        lat=lat,
        place_id=None,
        created_at=now,
    )


def test_cache_key_changes_with_avoid_flags() -> None:
    stops = [_stop("A", -63.1, 46.2, 0), _stop("B", -63.8, 46.4, 1)]
    trip_id = stops[0].trip_id
    now = datetime.now()
    base = TripSettingsOut(
        trip_id=trip_id,
        avoid_tolls=False,
        avoid_highways=False,
        avoid_ferries=False,
        costing="auto",
        optimize=False,
        selected_alternative=0,
        updated_at=now,
    )
    avoided = base.model_copy(update={"avoid_tolls": True})
    assert cache_key(stops, base, "v1") != cache_key(stops, avoided, "v1")
    assert cache_key(stops, base, "v1") != cache_key(stops, base, "v2")


def test_valhalla_payload_encodes_avoid_options() -> None:
    stops = [_stop("A", -63.1, 46.2, 0), _stop("B", -63.8, 46.4, 1)]
    settings = TripSettingsOut(
        trip_id=stops[0].trip_id,
        avoid_tolls=True,
        avoid_highways=True,
        avoid_ferries=True,
        costing="auto",
        optimize=False,
        selected_alternative=0,
        updated_at=datetime.now(),
    )
    body = valhalla_payload(stops, settings, optimized=False)
    assert body["alternates"] == 2
    assert body["costing_options"]["auto"] == {"use_highways": 0.0, "use_tolls": 0.0, "use_ferry": 0.0}


def test_decode_and_parse_valhalla() -> None:
    coords = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    assert coords
    payload = {
        "trip": {
            "summary": {"length": 12.3, "time": 900},
            "shape": "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
            "legs": [
                {
                    "maneuvers": [
                        {
                            "instruction": "Drive north",
                            "type": 1,
                            "length": 1.2,
                            "time": 60,
                            "begin_shape_index": 0,
                        }
                    ]
                }
            ],
        }
    }
    alternatives = parse_valhalla(payload)
    assert alternatives[0].distance_m == 12300
    assert alternatives[0].maneuvers[0].instruction == "Drive north"


def test_parse_optimized_order_uses_original_index() -> None:
    payload = {
        "trip": {
            "locations": [
                {"lat": 46.2, "lon": -63.1, "original_index": 0},
                {"lat": 46.5, "lon": -63.4, "original_index": 2},
                {"lat": 46.4, "lon": -63.8, "original_index": 1},
            ]
        }
    }
    assert parse_optimized_order(payload) == [0, 2, 1]
    assert parse_optimized_order({"trip": {}}) is None
