from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from rockyroad_api.db import Database
from rockyroad_api.models import Viewport
from rockyroad_api.photon import PhotonSearch, map_photon_features, photon_cache_key, photon_query_params
from rockyroad_api.search import SearchError
from rockyroad_api.settings import Settings


class FakeResponse:
    def __init__(self, status_code: int, payload: object | None = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, params: object = None, headers: object = None) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "headers": headers})
        if not self.responses:
            raise AssertionError("unexpected Photon call")
        return self.responses.pop(0)


def _settings(tmp_path: Path, **updates: object) -> Settings:
    values = {
        "duckdb_path": tmp_path / "rockyroad.duckdb",
        "geo_dir": tmp_path / "geo",
        "maps_dir": tmp_path / "maps",
        "osm_dir": tmp_path / "osm",
        "routing_dir": tmp_path / "routing",
        "provider_mode": "hosted",
        "photon_url": "https://photon.test",
        "photon_cache_ttl_s": 3600,
        "photon_cache_limit": 10,
        "max_search_results": 5,
    }
    values.update(updates)
    return Settings(**values)


def _feature(name: str, lon: float, lat: float, osm_id: int = 1) -> dict[str, object]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"name": name, "osm_type": "N", "osm_id": osm_id, "osm_value": "city"},
    }


def test_photon_params_filter_countries_and_bias_without_bbox() -> None:
    viewport = Viewport(west=-80, south=43, east=-79, north=44)
    items = photon_query_params("calgary", viewport, 8)
    assert ("q", "calgary") in items
    assert ("countrycode", "CA") in items
    assert ("countrycode", "US") in items
    assert ("lon", "-79.50000") in items
    assert ("lat", "43.50000") in items
    assert not any(key == "bbox" for key, _ in items)


def test_map_photon_features_skips_malformed() -> None:
    payload = {
        "features": [
            {
                "geometry": {"coordinates": [-114.07, 51.05]},
                "properties": {"name": "Calgary", "osm_type": "N", "osm_id": 9, "osm_value": "city"},
            },
            {"geometry": {"coordinates": ["bad"]}, "properties": {"name": "Nope"}},
            {"not": "a feature"},
        ]
    }
    result = map_photon_features(payload, query="calgary", limit=5)
    assert [place.name for place in result.results] == ["Calgary"]
    assert result.results[0].id == "photon:N:9"
    assert result.results[0].dataset == "photon"


def test_photon_search_caches_and_reuses(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    db = Database(settings)
    fake = FakeClient([FakeResponse(200, {"features": [_feature("Calgary", -114.07, 51.05)]})])
    search = PhotonSearch(settings, db, client=fake)  # type: ignore[arg-type]
    first = search.search("Calgary", Viewport(west=-115, south=50, east=-113, north=52))
    second = search.search("Calgary", Viewport(west=-115, south=50, east=-113, north=52))
    assert first.results[0].name == "Calgary"
    assert second.results[0].name == "Calgary"
    assert len(fake.calls) == 1
    db.close()


def test_photon_cache_key_coarsens_location_bias() -> None:
    near = Viewport(west=-114.08, south=51.04, east=-114.06, north=51.06)
    still_near = Viewport(west=-114.081, south=51.041, east=-114.061, north=51.061)
    far = Viewport(west=-80, south=43, east=-79, north=44)
    assert photon_cache_key("calgary", near) == photon_cache_key("calgary", still_near)
    assert photon_cache_key("calgary", near) != photon_cache_key("calgary", far)


def test_photon_upstream_errors(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    db = Database(settings)
    limited = PhotonSearch(settings, db, client=FakeClient([FakeResponse(429)]))  # type: ignore[arg-type]
    with pytest.raises(SearchError, match="rate limit") as quota:
        limited.search("calgary")
    assert quota.value.status_code == 429

    class TimeoutClient:
        def get(self, *args: object, **kwargs: object) -> FakeResponse:
            raise httpx.TimeoutException("slow")

    timed = PhotonSearch(settings, db, client=TimeoutClient())  # type: ignore[arg-type]
    with pytest.raises(SearchError, match="timed out") as exc:
        timed.search("calgary")
    assert exc.value.status_code == 503

    bad = PhotonSearch(settings, db, client=FakeClient([FakeResponse(200, {"no": "features"})]))  # type: ignore[arg-type]
    with pytest.raises(SearchError, match="unreadable"):
        bad.search("calgary")
    db.close()
