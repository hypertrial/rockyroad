from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from rockyroad_api.models import StopOut, TripSettingsOut
from rockyroad_api.ors import (
    MAX_ORS_STOPS,
    OpenRouteServiceClient,
    ors_avoid_features,
    ors_directions_payload,
    ors_failure_message,
    ors_optimization_payload,
    parse_ors_geojson,
    parse_vroom_order,
)
from rockyroad_api.providers import redact_secret
from rockyroad_api.routing import RoutingError
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


def _settings(stops: list[StopOut], **updates: object) -> TripSettingsOut:
    values = {
        "trip_id": stops[0].trip_id,
        "avoid_tolls": False,
        "avoid_highways": False,
        "avoid_ferries": False,
        "costing": "auto",
        "optimize": False,
        "selected_alternative": 0,
        "updated_at": datetime.now(),
    }
    values.update(updates)
    return TripSettingsOut(**values)


def _hosted_settings(tmp_path: Path, key: str = "test-key") -> Settings:
    return Settings(
        duckdb_path=tmp_path / "rockyroad.duckdb",
        geo_dir=tmp_path / "geo",
        maps_dir=tmp_path / "maps",
        osm_dir=tmp_path / "osm",
        routing_dir=tmp_path / "routing",
        provider_mode="hosted",
        ors_api_key=SecretStr(key),
        ors_base_url="https://ors.test",
        ors_optimization_url="https://ors.test/optimization",
    )


def _geojson_route() -> dict[str, object]:
    return {
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[-63.13, 46.24], [-114.07, 51.05]]},
                "properties": {
                    "summary": {"distance": 3600000, "duration": 129600},
                    "segments": [
                        {
                            "steps": [
                                {
                                    "instruction": "Head west",
                                    "type": 1,
                                    "distance": 3600000,
                                    "duration": 129600,
                                    "way_points": [0, 1],
                                }
                            ]
                        }
                    ],
                },
            }
        ]
    }


class FakeResponse:
    def __init__(self, status_code: int, payload: object | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or ("" if payload is None else str(payload))

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, json: object = None, headers: dict[str, str] | None = None) -> FakeResponse:
        self.calls.append({"url": url, "json": json, "headers": headers})
        if not self.responses:
            raise AssertionError("unexpected OpenRouteService call")
        return self.responses.pop(0)


def test_ors_payload_maps_avoid_options() -> None:
    stops = [_stop("A", -63.1, 46.2, 0), _stop("B", -114.07, 51.05, 1)]
    settings = _settings(stops, avoid_tolls=True, avoid_highways=True, avoid_ferries=True)
    assert ors_avoid_features(settings) == ["tollways", "highways", "ferries"]
    body = ors_directions_payload(stops, settings)
    assert body["coordinates"] == [[-63.1, 46.2], [-114.07, 51.05]]
    assert body["options"]["avoid_features"] == ["tollways", "highways", "ferries"]
    assert "alternative_routes" not in body


def test_ors_optimization_keeps_first_and_last_fixed() -> None:
    stops = [_stop("A", -63.1, 46.2, 0), _stop("B", -79.38, 43.65, 1), _stop("C", -114.07, 51.05, 2)]
    payload = ors_optimization_payload(stops)
    assert payload["vehicles"][0]["start"] == [-63.1, 46.2]
    assert payload["vehicles"][0]["end"] == [-114.07, 51.05]
    assert [job["id"] for job in payload["jobs"]] == [1]


def test_parse_ors_geojson_and_vroom_order() -> None:
    alternatives = parse_ors_geojson(_geojson_route())
    assert alternatives[0].distance_m == 3600000
    assert alternatives[0].maneuvers[0].instruction == "Head west"
    elevated = parse_ors_geojson(
        {
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[-63.13, 46.24, 12.0], [-114.07, 51.05, 8.0]]},
                    "properties": {"summary": {"distance": 1, "duration": 1}},
                }
            ]
        }
    )
    assert elevated[0].geometry["coordinates"] == [[-63.13, 46.24], [-114.07, 51.05]]
    order = parse_vroom_order(
        {
            "unassigned": [],
            "routes": [
                {
                    "steps": [
                        {"type": "start"},
                        {"type": "job", "id": 2},
                        {"type": "job", "id": 1},
                        {"type": "end"},
                    ]
                }
            ],
        },
        4,
    )
    assert order == [0, 2, 1, 3]


def test_parse_vroom_order_rejects_incomplete_results() -> None:
    with pytest.raises(RoutingError, match="every stop"):
        parse_vroom_order({"unassigned": [{"id": 1}], "routes": [{"steps": []}]}, 3)
    with pytest.raises(RoutingError, match="incomplete"):
        parse_vroom_order({"unassigned": [], "routes": [{"steps": [{"type": "job", "id": 1}]}]}, 4)


def test_ors_failure_and_redaction() -> None:
    secret = "super-secret-key"
    message, status = ors_failure_message(403, "quota exceeded for super-secret-key", secret=secret)
    assert "super-secret-key" not in message
    assert status == 429
    assert "quota" in message.casefold()
    assert redact_secret("Authorization: super-secret-key", secret) == "Authorization: [redacted]"
    assert ors_failure_message(429, "", secret=secret)[1] == 429
    assert ors_failure_message(401, "invalid", secret=secret)[1] == 503


@pytest.mark.parametrize(
    ("status_code", "body", "expected_message", "expected_status"),
    [
        (401, "Invalid API key", "rejected the API key", 503),
        (403, "Forbidden", "denied the request", 503),
        (403, "Daily quota exceeded", "daily quota is exhausted", 429),
        (429, "Too Many Requests", "rate limit reached", 429),
        (
            400,
            '{"error":{"code":2009,"message":"Routing failed"}}',
            "could not connect those stops",
            422,
        ),
        (400, '{"error":{"code":2016,"message":"Routing failed"}}', "could not connect those stops", 422),
        (400, '{"error":{"code":2010,"message":"Invalid point"}}', "No roads near", 422),
        (400, '{"error":{"code":2013,"message":"Invalid point"}}', "No roads near", 422),
        (400, '{"error":{"code":2014,"message":"Invalid point"}}', "No roads near", 422),
        (400, '{"error":{"code":2015,"message":"Invalid point"}}', "No roads near", 422),
        (400, '{"error":{"code":2004,"message":"Request exceeds limit"}}', "request limit", 422),
        (400, '{"error":{"code":2017,"message":"Request exceeds limit"}}', "request limit", 422),
        (413, "Request Entity Too Large", "request limit", 422),
        (422, "Unprocessable Content", "rejected RockyRoad's route request", 502),
        (418, "I'm a teapot", "rejected RockyRoad's route request", 502),
        (400, "Route could not be found", "could not connect those stops", 422),
        (400, "Point was not found", "No roads near", 422),
        (
            400,
            '{"error":{"code":2007,"message":"This response format is not supported"}}',
            "rejected RockyRoad's route request",
            502,
        ),
        (406, "Not Acceptable", "rejected RockyRoad's route request", 502),
        (500, "Internal Server Error", "could not produce a route", 503),
    ],
)
def test_ors_failure_maps_documented_provider_errors(
    status_code: int,
    body: str,
    expected_message: str,
    expected_status: int,
) -> None:
    message, mapped_status = ors_failure_message(status_code, body, secret="hidden-key")
    assert expected_message in message
    assert mapped_status == expected_status
    assert "hidden-key" not in message


def test_ors_client_two_stop_geojson_contract(tmp_path: Path) -> None:
    stops = [
        _stop("Richmond-Brighouse", -123.1362733, 49.1681069, 0),
        _stop("Calgary", -114.057541, 51.0456064, 1),
    ]
    fake = FakeClient([FakeResponse(200, _geojson_route())])
    client = OpenRouteServiceClient(_hosted_settings(tmp_path), client=fake)  # type: ignore[arg-type]

    result = client.request_route(stops, _settings(stops))

    assert result.alternatives[0].distance_m == 3600000
    assert len(fake.calls) == 1
    assert fake.calls[0]["url"] == "https://ors.test/v2/directions/driving-car/geojson"
    assert fake.calls[0]["json"] == {
        "coordinates": [[-123.1362733, 49.1681069], [-114.057541, 51.0456064]],
        "instructions": True,
        "geometry": True,
        "units": "m",
    }
    assert fake.calls[0]["headers"] == {
        "Authorization": "test-key",
        "Content-Type": "application/json",
        "Accept": "application/geo+json",
    }


def test_ors_client_maps_unroutable_response_without_leaking_secret(tmp_path: Path) -> None:
    secret = "hidden-key"
    stops = [_stop("A", -123.1362733, 49.1681069, 0), _stop("B", -114.057541, 51.0456064, 1)]
    response = FakeResponse(
        400,
        text=f'{{"error":{{"code":2009,"message":"Routing failed for {secret}"}}}}',
    )
    client = OpenRouteServiceClient(_hosted_settings(tmp_path, key=secret), client=FakeClient([response]))  # type: ignore[arg-type]

    with pytest.raises(RoutingError, match="could not connect those stops") as failure:
        client.request_route(stops, _settings(stops))

    assert failure.value.status_code == 422
    assert secret not in str(failure.value)


def test_ors_client_optimize_then_directions(tmp_path: Path) -> None:
    stops = [_stop("A", -63.1, 46.2, 0), _stop("B", -79.38, 43.65, 1), _stop("C", -114.07, 51.05, 2)]
    fake = FakeClient(
        [
            FakeResponse(200, {"unassigned": [], "routes": [{"steps": [{"type": "job", "id": 1}]}]}),
            FakeResponse(200, _geojson_route()),
        ]
    )
    client = OpenRouteServiceClient(_hosted_settings(tmp_path), client=fake)  # type: ignore[arg-type]
    result = client.request_route(stops, _settings(stops, optimize=True))
    assert result.optimized_order == [0, 1, 2]
    assert result.alternatives[0].distance_m == 3600000
    assert fake.calls[0]["url"] == "https://ors.test/optimization"
    body = fake.calls[1]["json"]
    assert isinstance(body, dict)
    assert body["coordinates"] == [[-63.1, 46.2], [-79.38, 43.65], [-114.07, 51.05]]
    assert body["coordinates"][0] == [-63.1, 46.2]
    headers = fake.calls[0]["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "test-key"
    assert headers["Accept"] == "application/json"
    direction_headers = fake.calls[1]["headers"]
    assert isinstance(direction_headers, dict)
    assert direction_headers["Accept"] == "application/geo+json"


def test_ors_client_rejects_too_many_stops_and_missing_key(tmp_path: Path) -> None:
    stops = [_stop(f"S{index}", -63.1, 46.2, index) for index in range(MAX_ORS_STOPS + 1)]
    client = OpenRouteServiceClient(_hosted_settings(tmp_path), client=FakeClient([]))  # type: ignore[arg-type]
    with pytest.raises(RoutingError, match="at most 50") as exc:
        client.request_route(stops, _settings(stops))
    assert exc.value.status_code == 422
    empty = OpenRouteServiceClient(_hosted_settings(tmp_path, key=""), client=FakeClient([]))  # type: ignore[arg-type]
    with pytest.raises(RoutingError, match="API key is missing") as missing:
        empty.request_route(stops[:2], _settings(stops[:2]))
    assert missing.value.status_code == 503
    assert "test-key" not in str(missing.value)


def test_ors_client_maps_timeout_and_quota(tmp_path: Path) -> None:
    class TimeoutClient:
        def post(self, *args: object, **kwargs: object) -> FakeResponse:
            raise httpx.TimeoutException("slow")

    client = OpenRouteServiceClient(_hosted_settings(tmp_path, key="hidden-key"), client=TimeoutClient())  # type: ignore[arg-type]
    with pytest.raises(RoutingError, match="timed out") as timed:
        client.request_route(
            [_stop("A", -63.1, 46.2, 0), _stop("B", -114.07, 51.05, 1)],
            _settings([_stop("A", -63.1, 46.2, 0), _stop("B", -114.07, 51.05, 1)]),
        )
    assert timed.value.status_code == 503
    assert "hidden-key" not in str(timed.value)

    quota = OpenRouteServiceClient(
        _hosted_settings(tmp_path, key="hidden-key"),
        client=FakeClient([FakeResponse(403, text="daily quota exceeded hidden-key")]),  # type: ignore[arg-type]
    )
    stops = [_stop("A", -63.1, 46.2, 0), _stop("B", -114.07, 51.05, 1)]
    with pytest.raises(RoutingError, match="quota") as exhausted:
        quota.request_route(stops, _settings(stops))
    assert exhausted.value.status_code == 429
    assert "hidden-key" not in str(exhausted.value)


def test_ors_client_maps_network_failure_to_service_unavailable(tmp_path: Path) -> None:
    class NetworkFailureClient:
        def post(self, *args: object, **kwargs: object) -> FakeResponse:
            raise httpx.ConnectError("connection refused")

    stops = [_stop("A", -123.1362733, 49.1681069, 0), _stop("B", -114.057541, 51.0456064, 1)]
    client = OpenRouteServiceClient(_hosted_settings(tmp_path), client=NetworkFailureClient())  # type: ignore[arg-type]

    with pytest.raises(RoutingError, match="unavailable") as failure:
        client.request_route(stops, _settings(stops))

    assert failure.value.status_code == 503
