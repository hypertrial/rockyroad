from __future__ import annotations

import json
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rockyroad_api.main import create_app
from rockyroad_api.models import Maneuver, RouteAlternative
from rockyroad_api.routing import RouteComputation
from rockyroad_api.settings import Settings


def test_health_and_trip_roundtrip(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "degraded"
    assert "bounds" in health.json()
    assert "update-osm --profile sample" in (health.json()["detail"] or "")
    assert health.json()["bounds"] is None
    assert health.json()["profile"] is None
    maps = client.get("/maps/north-america.pmtiles")
    assert maps.status_code == 404
    created = client.post("/api/trips", json={"name": "Cabot loop"})
    assert created.status_code == 201
    trip_id = created.json()["id"]
    updated = client.put(
        f"/api/trips/{trip_id}/stops",
        json=[
            {"name": "Charlottetown", "lon": -63.131, "lat": 46.238},
            {"name": "Cavendish", "lon": -63.45, "lat": 46.49},
        ],
    )
    assert updated.status_code == 200
    assert len(updated.json()["stops"]) == 2


def test_health_bounds_use_settings_osm_dir(settings: Settings) -> None:
    (settings.osm_dir / "manifest.json").write_text(json.dumps({"profile": "sample"}), encoding="utf-8")
    with TestClient(create_app(settings)) as client:
        payload = client.get("/api/health").json()
    assert payload["bounds"] == [-64.45, 45.9, -61.9, 47.1]
    assert payload["profile"] == "sample"


def test_health_bounds_absent_without_osm_manifest(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        payload = client.get("/api/health").json()
    assert payload["bounds"] is None


def test_route_uses_valhalla_and_caches(client: TestClient) -> None:
    created = client.post("/api/trips", json={"name": "Route me"})
    trip_id = created.json()["id"]
    client.put(
        f"/api/trips/{trip_id}/stops",
        json=[
            {"name": "A", "lon": -63.131, "lat": 46.238},
            {"name": "B", "lon": -63.79, "lat": 46.393},
        ],
    )
    fake = RouteAlternative(
        index=0,
        distance_m=40000,
        duration_s=2400,
        geometry={"type": "LineString", "coordinates": [[-63.13, 46.24], [-63.79, 46.39]]},
        maneuvers=[Maneuver(instruction="Head west", type=1, distance_m=40000, duration_s=2400)],
    )
    app = client.app
    assert isinstance(app, FastAPI)
    app.state.valhalla.request_route = MagicMock(return_value=RouteComputation(alternatives=[fake]))
    first = client.post(f"/api/trips/{trip_id}/route")
    second = client.post(f"/api/trips/{trip_id}/route")
    assert first.status_code == 200
    assert first.json()["cache_hit"] is False
    assert second.json()["cache_hit"] is True
    assert app.state.valhalla.request_route.call_count == 1


def test_optimize_persists_valhalla_stop_order(client: TestClient) -> None:
    created = client.post("/api/trips", json={"name": "Optimize me"})
    trip_id = created.json()["id"]
    client.put(
        f"/api/trips/{trip_id}/stops",
        json=[
            {"name": "A", "lon": -63.131, "lat": 46.238},
            {"name": "B", "lon": -63.79, "lat": 46.393},
            {"name": "C", "lon": -63.45, "lat": 46.49},
        ],
    )
    fake = RouteAlternative(
        index=0,
        distance_m=50000,
        duration_s=3000,
        geometry={"type": "LineString", "coordinates": [[-63.13, 46.24], [-63.45, 46.49], [-63.79, 46.39]]},
        maneuvers=[Maneuver(instruction="Loop", type=1, distance_m=50000, duration_s=3000)],
    )
    app = client.app
    assert isinstance(app, FastAPI)
    app.state.valhalla.request_route = MagicMock(
        return_value=RouteComputation(alternatives=[fake], optimized_order=[0, 2, 1])
    )
    response = client.post(f"/api/trips/{trip_id}/optimize")
    assert response.status_code == 200
    trip = client.get(f"/api/trips/{trip_id}").json()
    assert [stop["name"] for stop in trip["stops"]] == ["A", "C", "B"]
    assert [stop["position"] for stop in trip["stops"]] == [0, 1, 2]
    assert trip["settings"]["optimize"] is True
    assert trip["route"] is not None
    assert trip["route"]["cache_hit"] is True
    assert trip["route"]["alternatives"][0]["distance_m"] == 50000


def test_route_rejects_stops_outside_sample_extract(client: TestClient, settings: Settings) -> None:
    (settings.osm_dir / "manifest.json").write_text(json.dumps({"profile": "sample"}), encoding="utf-8")
    created = client.post("/api/trips", json={"name": "Prairie"})
    trip_id = created.json()["id"]
    client.put(
        f"/api/trips/{trip_id}/stops",
        json=[
            {"name": "Calgary", "lon": -114.07, "lat": 51.05},
            {"name": "Edmonton", "lon": -113.49, "lat": 53.54},
        ],
    )
    response = client.post(f"/api/trips/{trip_id}/route")
    assert response.status_code == 422
    assert "Prince Edward Island" in response.json()["detail"]
