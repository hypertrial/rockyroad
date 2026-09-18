from __future__ import annotations

import math
from pathlib import Path

import httpx
import pytest

from rockyroad_api.db import Database
from rockyroad_api.models import PlaceResult, SearchResponse, Viewport
from rockyroad_api.photon import (
    DEDUPE_RADIUS_KM,
    PhotonSearch,
    dedupe_results,
    format_region,
    map_photon_features,
    photon_cache_key,
    photon_query_params,
    rank_in_view,
)
from rockyroad_api.search import SearchError, haversine_km
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


def _feature(
    name: str,
    lon: float,
    lat: float,
    osm_id: int = 1,
    **properties: object,
) -> dict[str, object]:
    payload = {"name": name, "osm_type": "N", "osm_id": osm_id, "osm_value": "city", "type": "city"}
    payload.update(properties)
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": payload,
    }


def _place(
    name: str,
    lon: float,
    lat: float,
    *,
    state: str | None = None,
    country: str | None = None,
    country_code: str | None = None,
    county: str | None = None,
    place_type: str | None = "city",
    score: float = 1.0,
) -> PlaceResult:
    return PlaceResult(
        id=f"photon:{name}:{lon}:{lat}",
        name=name,
        feature_type="city",
        dataset="photon",
        lon=lon,
        lat=lat,
        score=score,
        state=state,
        country=country,
        country_code=country_code,
        county=county,
        place_type=place_type,
    )


def test_photon_params_filter_countries_and_bias_without_bbox() -> None:
    viewport = Viewport(west=-80, south=43, east=-79, north=44)
    items = photon_query_params("calgary", viewport, 8)
    assert ("q", "calgary") in items
    assert ("countrycode", "CA") in items
    assert ("countrycode", "US") in items
    assert ("lon", "-79.50000") in items
    assert ("lat", "43.50000") in items
    assert not any(key == "bbox" for key, _ in items)


def test_photon_search_skips_blank_queries_without_calling_upstream(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    db = Database(settings)
    fake = FakeClient([])
    search = PhotonSearch(settings, db, client=fake)  # type: ignore[arg-type]
    assert search.search("   ").results == []
    assert fake.calls == []
    db.close()


def test_map_photon_features_falls_back_for_blank_names_and_admin() -> None:
    payload = {
        "features": [
            {
                "geometry": {"coordinates": [-114.07, 51.05]},
                "properties": {
                    "name": "  ",
                    "housenumber": "12",
                    "street": "Main St",
                    "osm_type": "N",
                    "osm_id": 1,
                    "state": "  ",
                    "country": "Canada",
                    "type": "house",
                },
            },
            {
                "geometry": {"coordinates": [-114.08, 51.06]},
                "properties": {"name": "", "osm_type": "N", "country": "Canada"},
            },
            {
                "geometry": {"coordinates": [-114.09, 51.07]},
                "properties": {"osm_type": "N", "osm_id": 3},
            },
        ]
    }
    result = map_photon_features(payload, query="main", limit=5)
    assert [place.name for place in result.results] == ["12 Main St", "Canada", "Unnamed place"]
    assert result.results[0].state is None
    assert result.results[0].region == "Canada"
    assert result.results[1].id == "photon:Canada:-114.08000:51.06000"
    assert result.results[2].id == "photon:N:3"


def test_map_photon_features_skips_malformed() -> None:
    payload = {
        "features": [
            {
                "geometry": {"coordinates": [-114.07, 51.05]},
                "properties": {"name": "Calgary", "osm_type": "N", "osm_id": 9, "osm_value": "city"},
            },
            {"geometry": {"coordinates": ["bad"]}, "properties": {"name": "Nope"}},
            _feature("NaN", float("nan"), 51.05, 10),
            _feature("Infinite", -114.07, float("inf"), 11),
            _feature("Invalid longitude", 181, 51.05, 12),
            _feature("Invalid latitude", -114.07, -91, 13),
            _feature("Overflow", 10**400, 51.05, 14),
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


def test_map_photon_features_keeps_admin_context_for_same_name_cities() -> None:
    payload = {
        "features": [
            _feature(
                "Vancouver",
                -123.1139,
                49.2609,
                1,
                state="British Columbia",
                country="Canada",
                countrycode="CA",
                type="city",
            ),
            _feature(
                "Vancouver",
                -122.675,
                45.6307,
                2,
                state="Washington",
                country="United States",
                countrycode="US",
                type="city",
            ),
        ]
    }
    result = map_photon_features(payload, query="vancouver", limit=5)
    assert [place.region for place in result.results] == [
        "British Columbia, Canada",
        "Washington, United States",
    ]
    assert result.results[0].state == "British Columbia"
    assert result.results[0].country_code == "CA"
    assert result.results[1].country == "United States"


def test_format_region_varies_by_place_type_and_same_state_tiebreak() -> None:
    country = _place("Canada", -96, 60, place_type="country", country="Canada")
    state = _place("British Columbia", -123, 54, place_type="state", country="Canada")
    county = _place(
        "King County",
        -122.2,
        47.5,
        place_type="county",
        state="Washington",
        country="United States",
    )
    missing = _place("Somewhere", -100, 50, place_type="city", country="Canada")
    assert format_region(country) is None
    assert format_region(_place("Canada", -96, 60, place_type="COUNTRY", country="Canada")) is None
    assert format_region(state) == "Canada"
    assert format_region(_place("British Columbia", -123, 54, place_type="State", country="Canada")) == "Canada"
    assert format_region(county) == "Washington, United States"
    assert format_region(missing) == "Canada"
    assert format_region(_place("Nowhere", -100, 50, place_type="city")) is None

    springfield_clark = _place(
        "Springfield",
        -83.8,
        39.92,
        state="Ohio",
        country="United States",
        county="Clark County",
    )
    springfield_summit = _place(
        "Springfield",
        -81.43,
        41.03,
        state="Ohio",
        country="United States",
        county="Summit County",
    )
    mapped = map_photon_features(
        {
            "features": [
                _feature(
                    "Springfield",
                    -83.8,
                    39.92,
                    1,
                    state="Ohio",
                    country="United States",
                    countrycode="US",
                    county="Clark County",
                    type="city",
                ),
                _feature(
                    "Springfield",
                    -81.43,
                    41.03,
                    2,
                    state="Ohio",
                    country="United States",
                    countrycode="US",
                    county="Summit County",
                    type="city",
                ),
            ]
        },
        query="springfield",
        limit=5,
    )
    assert [place.region for place in mapped.results] == [
        "Clark County, Ohio, United States",
        "Summit County, Ohio, United States",
    ]
    assert format_region(springfield_clark, include_county=True) == "Clark County, Ohio, United States"
    assert format_region(springfield_summit, include_county=True) == "Summit County, Ohio, United States"


def test_dedupe_results_collapses_nearby_same_place_and_keeps_other_states() -> None:
    node = _place("Calgary", -114.071, 51.045, state="Alberta", country_code="CA")
    relation = _place("Calgary", -114.08, 51.05, state="Alberta", country_code="CA")
    distant = _place("Calgary", -110.0, 50.0, state="Alberta", country_code="CA")
    other_state = _place("Portland", -122.68, 45.52, state="Oregon", country_code="US")
    other_state_twin = _place("Portland", -70.26, 43.66, state="Maine", country_code="US")
    kept = dedupe_results([node, relation, distant, other_state, other_state_twin])
    assert [place.id for place in kept] == [node.id, distant.id, other_state.id, other_state_twin.id]


def test_dedupe_results_uses_inclusive_two_kilometer_radius() -> None:
    lon, lat = -114.071, 51.045
    origin = _place("Calgary", lon, lat, state="Alberta", country_code="CA")
    under = _place(
        "Calgary",
        lon,
        lat + (DEDUPE_RADIUS_KM * 0.999) / 6371.0 * (180.0 / math.pi),
        state="Alberta",
        country_code="CA",
    )
    over = _place(
        "Calgary",
        lon,
        lat + (DEDUPE_RADIUS_KM * 1.001) / 6371.0 * (180.0 / math.pi),
        state="Alberta",
        country_code="CA",
    )
    assert haversine_km(lon, lat, under.lon, under.lat) < DEDUPE_RADIUS_KM
    assert haversine_km(lon, lat, over.lon, over.lat) > DEDUPE_RADIUS_KM
    assert [place.id for place in dedupe_results([origin, under])] == [origin.id]
    assert [place.id for place in dedupe_results([origin, over])] == [origin.id, over.id]


def test_dedupe_results_requires_same_country_and_treats_blank_state_as_equal() -> None:
    node = _place("Calgary", -114.071, 51.045, state="Alberta", country_code="CA")
    same = _place("CALGARY", -114.072, 51.046, state="alberta", country_code="ca")
    other_country = _place("Calgary", -114.072, 51.046, state="Alberta", country_code="US")
    blank = _place("Pin", -114.071, 51.045, state=None, country_code="CA")
    empty = _place("pin", -114.072, 51.046, state="", country_code="CA")
    kept = dedupe_results([node, same, other_country, blank, empty])
    assert [place.id for place in kept] == [node.id, other_country.id, blank.id]


def test_assign_regions_adds_county_only_for_same_state_collisions() -> None:
    lone = map_photon_features(
        {
            "features": [
                _feature(
                    "Calgary",
                    -114.07,
                    51.05,
                    1,
                    state="Alberta",
                    country="Canada",
                    countrycode="CA",
                    county="Division No. 6",
                    type="city",
                )
            ]
        },
        query="calgary",
        limit=5,
    )
    assert [place.region for place in lone.results] == ["Alberta, Canada"]

    crossed = map_photon_features(
        {
            "features": [
                _feature(
                    "springfield",
                    -83.8,
                    39.92,
                    1,
                    state="Ohio",
                    country="United States",
                    countrycode="US",
                    county="Clark County",
                    type="city",
                ),
                _feature(
                    "Springfield",
                    -89.65,
                    39.78,
                    2,
                    state="Illinois",
                    country="United States",
                    countrycode="US",
                    county="Sangamon County",
                    type="city",
                ),
            ]
        },
        query="springfield",
        limit=5,
    )
    assert [place.region for place in crossed.results] == [
        "Ohio, United States",
        "Illinois, United States",
    ]


def test_viewport_contains_handles_antimeridian_and_rank_in_view() -> None:
    wrap = Viewport(west=170, south=50, east=-170, north=55)
    assert wrap.contains(175, 52) is True
    assert wrap.contains(0, 52) is False
    assert wrap.contains(*wrap.center) is True
    assert abs(wrap.center[0]) >= 170
    gulf = Viewport(west=-1, south=50, east=1, north=55)
    assert photon_cache_key("adak", wrap) != photon_cache_key("adak", gulf)
    params = dict(photon_query_params("adak", wrap, 8))
    assert abs(float(params["lon"])) >= 170
    assert params["lat"] == "52.50000"
    outside_first = _place("Vancouver", -122.675, 45.6307, state="Washington", score=1.0)
    inside = _place("Vancouver", -123.1139, 49.2609, state="British Columbia", score=0.98)
    response = rank_in_view(
        SearchResponse(query="vancouver", results=[outside_first, inside]),
        Viewport(west=-124, south=48, east=-122, north=50),
    )
    assert [place.name for place in response.results] == ["Vancouver", "Vancouver"]
    assert response.results[0].state == "British Columbia"
    assert [place.score for place in response.results] == [1.0, 0.98]
    unchanged = rank_in_view(SearchResponse(query="vancouver", results=[outside_first, inside]), None)
    assert [place.state for place in unchanged.results] == ["Washington", "British Columbia"]


def test_viewport_center_wraps_into_each_hemisphere() -> None:
    western = Viewport(west=170, south=50, east=-160, north=55)
    assert western.center == (-175.0, 52.5)
    assert western.contains(*western.center) is True
    assert western.contains(5.0, 52.5) is False

    eastern = Viewport(west=160, south=50, east=-170, north=55)
    assert eastern.center == (175.0, 52.5)
    assert eastern.contains(*eastern.center) is True
    assert eastern.contains(-5.0, 52.5) is False

    dateline = Viewport(west=170, south=50, east=-170, north=55)
    assert photon_cache_key("adak", western) != photon_cache_key("adak", dateline)
    assert photon_cache_key("adak", eastern) != photon_cache_key("adak", dateline)
    params = dict(photon_query_params("adak", western, 8))
    assert params["lon"] == "-175.00000"
    assert params["lat"] == "52.50000"


def test_viewport_contains_includes_edges_and_ranks_boundary_points_as_inside() -> None:
    box = Viewport(west=-124, south=48, east=-122, north=50)
    assert box.contains(-124, 49) is True
    assert box.contains(-122, 49) is True
    assert box.contains(-123, 48) is True
    assert box.contains(-123, 50) is True
    assert box.contains(-124.0001, 49) is False
    assert box.contains(-121.9999, 49) is False
    assert box.contains(-123, 47.9999) is False
    assert box.contains(-123, 50.0001) is False

    wrap = Viewport(west=170, south=50, east=-170, north=55)
    assert wrap.contains(170, 52) is True
    assert wrap.contains(-170, 52) is True
    assert wrap.contains(169.999, 52) is False
    assert wrap.contains(-169.999, 52) is False
    assert wrap.contains(175, 49.999) is False
    assert wrap.contains(175, 55.001) is False

    edge = _place("Edge", -124, 49, state="British Columbia", score=0.98)
    outside = _place("Outside", -125, 49, state="Alaska", score=1.0)
    ranked = rank_in_view(SearchResponse(query="edge", results=[outside, edge]), box)
    assert [place.name for place in ranked.results] == ["Edge", "Outside"]
    assert [place.score for place in ranked.results] == [1.0, 0.98]


def test_photon_cache_hit_re_ranks_without_a_second_request(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    db = Database(settings)
    payload = {
        "features": [
            _feature(
                "Vancouver",
                -122.675,
                45.6307,
                2,
                state="Washington",
                country="United States",
                countrycode="US",
            ),
            _feature(
                "Vancouver",
                -123.1139,
                49.2609,
                1,
                state="British Columbia",
                country="Canada",
                countrycode="CA",
            ),
        ]
    }
    fake = FakeClient([FakeResponse(200, payload)])
    search = PhotonSearch(settings, db, client=fake)  # type: ignore[arg-type]
    tight = Viewport(west=-124, south=48, east=-122, north=50)
    wide = Viewport(west=-124, south=45, east=-122, north=53)
    assert photon_cache_key("vancouver", tight) == photon_cache_key("vancouver", wide)
    first = search.search("vancouver", tight)
    second = search.search("vancouver", wide)
    assert len(fake.calls) == 1
    assert first.results[0].region == "British Columbia, Canada"
    assert [place.region for place in second.results] == [
        "Washington, United States",
        "British Columbia, Canada",
    ]
    db.close()


def test_map_photon_features_ignores_non_string_admin_and_caps_names() -> None:
    payload = {
        "features": [
            _feature(
                "A" * 240,
                -114.07,
                51.05,
                1,
                state={"name": "Alberta"},
                country="Canada",
                countrycode="CA",
                type="city",
            )
        ]
    }
    result = map_photon_features(payload, query="calgary", limit=1)
    assert result.results[0].name == "A" * 200
    assert result.results[0].state is None
    assert result.results[0].region == "Canada"


def test_old_cached_payloads_accept_missing_admin_fields() -> None:
    response = SearchResponse.model_validate(
        {
            "query": "calgary",
            "results": [
                {
                    "id": "photon:N:1",
                    "name": "Calgary",
                    "feature_type": "city",
                    "dataset": "photon",
                    "lon": -114.07,
                    "lat": 51.05,
                    "score": 1.0,
                }
            ],
        }
    )
    place = response.results[0]
    assert place.region is None
    assert place.state is None
    assert place.country is None
    assert place.city is None
    assert place.country_code is None
    assert place.place_type is None
