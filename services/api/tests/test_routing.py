from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import httpx
import pytest

from rockyroad_api.models import StopOut, TripSettingsOut
from rockyroad_api.polyline import decode_polyline
from rockyroad_api.routing import (
    RoutingError,
    ValhallaClient,
    cache_key,
    parse_optimized_order,
    parse_valhalla,
    routing_data_version,
    routing_failure_message,
    valhalla_payload,
)
from rockyroad_api.settings import Settings


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


def test_hosted_routing_version_is_independent_of_valhalla_manifest(tmp_path) -> None:
    settings = Settings(
        duckdb_path=tmp_path / "db",
        geo_dir=tmp_path / "geo",
        maps_dir=tmp_path / "maps",
        osm_dir=tmp_path / "osm",
        routing_dir=tmp_path / "routing",
        provider_mode="hosted",
        hosted_routing_version="ors-v1",
    )
    (settings.routing_dir).mkdir(parents=True, exist_ok=True)
    (settings.routing_dir / "manifest.json").write_text('{"version":"valhalla-old"}', encoding="utf-8")
    assert routing_data_version(settings) == "ors-v1"


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
    assert body["locations"][0]["radius"] == 5000
    assert body["locations"][0]["minimum_reachability"] == 0


def test_routing_failure_message_explains_missing_edges() -> None:
    sample = routing_failure_message(
        400,
        '{"error_code":171,"error":"No suitable edges near location"}',
        profile="sample",
    )
    continental = routing_failure_message(
        400,
        '{"error_code":171,"error":"No suitable edges near location"}',
        profile="canada-usa",
    )
    assert "Prince Edward Island" in sample
    assert "171" not in sample
    assert "canada-usa" in continental
    assert "Prince Edward Island" not in continental
    assert "no details" in routing_failure_message(503, "")


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


@pytest.mark.parametrize(
    "body",
    [
        "not-json",
        {"trip": "not-an-object"},
        {"trip": {"summary": {}, "shape": "_"}},
        {"trip": {"summary": {}, "legs": "not-a-list"}},
    ],
    ids=["invalid-json", "invalid-trip", "truncated-shape", "invalid-legs"],
)
def test_valhalla_client_translates_malformed_success_response(tmp_path, body) -> None:
    settings = Settings(
        duckdb_path=tmp_path / "db",
        geo_dir=tmp_path / "geo",
        maps_dir=tmp_path / "maps",
        osm_dir=tmp_path / "osm",
        routing_dir=tmp_path / "routing",
    )

    def response(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body) if isinstance(body, str) else httpx.Response(200, json=body)

    client = httpx.Client(transport=httpx.MockTransport(response))
    trip_settings = TripSettingsOut(
        trip_id=uuid4(),
        avoid_tolls=False,
        avoid_highways=False,
        avoid_ferries=False,
        costing="auto",
        optimize=False,
        selected_alternative=0,
        updated_at=datetime.now(),
    )
    with pytest.raises(RoutingError, match="unreadable") as exc:
        ValhallaClient(settings, client).request_route(
            [_stop("A", -63.1, 46.2, 0), _stop("B", -63.8, 46.4, 1)],
            trip_settings,
        )
    assert exc.value.status_code == 502
