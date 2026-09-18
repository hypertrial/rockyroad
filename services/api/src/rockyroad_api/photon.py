from __future__ import annotations

import hashlib
import json
import math
from typing import Any, cast

import httpx

from rockyroad_api.db import Database
from rockyroad_api.models import PlaceResult, SearchResponse, Viewport
from rockyroad_api.search import SearchError, haversine_km
from rockyroad_api.settings import Settings

PHOTON_COUNTRIES = ("CA", "US")
DEDUPE_RADIUS_KM = 2.0
_NAME_MAX = 200
_ADMIN_MAX = 80
_REGION_MAX = 200


def photon_cache_key(query: str, viewport: Viewport | None) -> str:
    center = None
    if viewport is not None:
        lon, lat = viewport.center
        center = (round(lon, 2), round(lat, 2))
    encoded = json.dumps({"q": query.casefold(), "center": center}, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def photon_query_params(query: str, viewport: Viewport | None, limit: int) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = [
        ("q", query),
        ("limit", str(limit)),
        ("lang", "en"),
        ("countrycode", PHOTON_COUNTRIES[0]),
        ("countrycode", PHOTON_COUNTRIES[1]),
    ]
    if viewport is not None:
        lon, lat = viewport.center
        params.extend([("lon", f"{lon:.5f}"), ("lat", f"{lat:.5f}")])
    return params


def map_photon_features(payload: dict[str, Any], *, query: str, limit: int) -> SearchResponse:
    features = payload.get("features")
    if not isinstance(features, list):
        raise SearchError("Photon returned an unreadable response.", status_code=502)
    results: list[PlaceResult] = []
    for index, feature in enumerate(features):
        if len(results) >= limit:
            break
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        properties = feature.get("properties")
        if not isinstance(geometry, dict) or not isinstance(properties, dict):
            continue
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            continue
        try:
            lon = float(coordinates[0])
            lat = float(coordinates[1])
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(lon) or not math.isfinite(lat) or not -180 <= lon <= 180 or not -90 <= lat <= 90:
            continue
        name = _photon_name(properties)
        osm_type = str(properties.get("osm_type") or "x")
        osm_id = properties.get("osm_id")
        place_id = f"photon:{osm_type}:{osm_id}" if osm_id is not None else f"photon:{name}:{lon:.5f}:{lat:.5f}"
        raw_type = properties.get("osm_value") or properties.get("osm_key") or properties.get("type")
        feature_type = _photon_text(raw_type) or "place"
        score = max(0.0, 1.0 - index * 0.02)
        results.append(
            PlaceResult(
                id=place_id,
                name=name,
                feature_type=feature_type,
                dataset="photon",
                lon=lon,
                lat=lat,
                score=round(score, 6),
                population=None,
                city=_photon_text(properties.get("city")),
                county=_photon_text(properties.get("county")),
                state=_photon_text(properties.get("state")),
                country=_photon_text(properties.get("country")),
                country_code=_photon_text(properties.get("countrycode")),
                place_type=_photon_text(properties.get("type")),
            )
        )
    results = dedupe_results(results)
    assign_regions(results)
    return SearchResponse(query=query, results=results)


def _photon_text(value: Any, *, limit: int = _ADMIN_MAX) -> str | None:
    if not isinstance(value, str):
        return None
    chars: list[str] = []
    for character in value[: limit + 32]:
        if not character.isprintable() or (not chars and character.isspace()):
            continue
        chars.append(character)
        if len(chars) >= limit:
            break
    while chars and chars[-1].isspace():
        chars.pop()
    return "".join(chars) or None


def format_region(result: PlaceResult, *, include_county: bool = False) -> str | None:
    place_type = (result.place_type or "").casefold()
    if place_type == "country":
        return None
    parts: list[str] = []
    if place_type == "state":
        if result.country:
            parts.append(result.country)
    else:
        if include_county and result.county:
            parts.append(result.county)
        if result.state:
            parts.append(result.state)
        if result.country:
            parts.append(result.country)
    if not parts:
        return None
    return ", ".join(parts)[:_REGION_MAX]


def assign_regions(results: list[PlaceResult]) -> None:
    counts: dict[tuple[str, str], int] = {}
    for result in results:
        key = (result.name.casefold(), (result.state or "").casefold())
        counts[key] = counts.get(key, 0) + 1
    for result in results:
        key = (result.name.casefold(), (result.state or "").casefold())
        result.region = format_region(result, include_county=counts[key] > 1)


def dedupe_results(results: list[PlaceResult]) -> list[PlaceResult]:
    kept: list[PlaceResult] = []
    for result in results:
        if any(_is_near_duplicate(result, existing) for existing in kept):
            continue
        kept.append(result)
    return kept


def _is_near_duplicate(candidate: PlaceResult, existing: PlaceResult) -> bool:
    if candidate.name.casefold() != existing.name.casefold():
        return False
    if (candidate.state or "").casefold() != (existing.state or "").casefold():
        return False
    if (candidate.country_code or "").casefold() != (existing.country_code or "").casefold():
        return False
    return haversine_km(candidate.lon, candidate.lat, existing.lon, existing.lat) <= DEDUPE_RADIUS_KM


def rank_in_view(response: SearchResponse, viewport: Viewport | None) -> SearchResponse:
    if viewport is None:
        return response
    inside = [result for result in response.results if viewport.contains(result.lon, result.lat)]
    outside = [result for result in response.results if not viewport.contains(result.lon, result.lat)]
    ordered = [
        result.model_copy(update={"score": round(max(0.0, 1.0 - index * 0.02), 6)})
        for index, result in enumerate([*inside, *outside])
    ]
    return SearchResponse(query=response.query, results=ordered)


def _photon_name(properties: dict[str, Any]) -> str:
    name = _photon_text(properties.get("name"), limit=_NAME_MAX)
    if name:
        return name
    street = " ".join(
        part
        for part in (
            _photon_text(properties.get("housenumber"), limit=_ADMIN_MAX) or "",
            _photon_text(properties.get("street"), limit=_ADMIN_MAX) or "",
        )
        if part
    )
    if street:
        return street[:_NAME_MAX]
    for key in ("city", "locality", "state", "country"):
        value = _photon_text(properties.get(key), limit=_NAME_MAX)
        if value:
            return value
    return "Unnamed place"


class PhotonSearch:
    def __init__(self, settings: Settings, db: Database, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.db = db
        self.client = client or httpx.Client(
            timeout=settings.photon_timeout_s,
            headers={"User-Agent": settings.photon_user_agent},
        )

    def search(self, query: str, viewport: Viewport | None = None) -> SearchResponse:
        cleaned = " ".join(query.split())
        if not cleaned:
            return SearchResponse(query=query, results=[])
        key = photon_cache_key(cleaned, viewport)
        cached = self._load_cache(key)
        if cached is not None:
            return rank_in_view(cached, viewport)
        payload = self._request(cleaned, viewport)
        result = map_photon_features(payload, query=cleaned, limit=self.settings.max_search_results)
        self._store_cache(key, cleaned, result)
        return rank_in_view(result, viewport)

    def _request(self, query: str, viewport: Viewport | None) -> dict[str, Any]:
        url = f"{self.settings.photon_url.rstrip('/')}/api"
        try:
            params = cast(
                list[tuple[str, str | int | float | bool | None]],
                photon_query_params(query, viewport, self.settings.max_search_results),
            )
            response = self.client.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise SearchError("Photon search timed out.", status_code=503) from exc
        except httpx.HTTPError as exc:
            raise SearchError("Photon search is unavailable.", status_code=503) from exc
        if response.status_code == 429:
            raise SearchError("Photon rate limit reached. Wait a moment and try again.", status_code=429)
        if response.status_code >= 400:
            raise SearchError("Photon search is unavailable.", status_code=503)
        try:
            payload = response.json()
        except ValueError as exc:
            raise SearchError("Photon returned an unreadable response.", status_code=502) from exc
        if not isinstance(payload, dict):
            raise SearchError("Photon returned an unreadable response.", status_code=502)
        return payload

    def _load_cache(self, key: str) -> SearchResponse | None:
        ttl = max(1, self.settings.photon_cache_ttl_s)

        def _read(conn: Any) -> SearchResponse | None:
            row = conn.execute(
                """
                SELECT payload FROM search_cache
                WHERE cache_key = ? AND created_at > now() - (CAST(? AS INTEGER) * INTERVAL 1 SECOND)
                """,
                [key, ttl],
            ).fetchone()
            if row is None:
                return None
            payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            return SearchResponse.model_validate(payload)

        try:
            return self.db.read(_read)
        except Exception:
            return None

    def _store_cache(self, key: str, query: str, result: SearchResponse) -> None:
        ttl = max(1, self.settings.photon_cache_ttl_s)
        limit = max(1, self.settings.photon_cache_limit)
        encoded = result.model_dump_json()

        def _write(conn: Any) -> None:
            conn.execute(
                """
                INSERT INTO search_cache VALUES (?, ?, ?::JSON, now())
                ON CONFLICT (cache_key) DO UPDATE SET
                    query = excluded.query,
                    payload = excluded.payload,
                    created_at = now()
                """,
                [key, query, encoded],
            )
            conn.execute(
                "DELETE FROM search_cache WHERE created_at < now() - (CAST(? AS INTEGER) * INTERVAL 1 SECOND)",
                [ttl],
            )
            conn.execute(
                """
                DELETE FROM search_cache
                WHERE cache_key IN (
                    SELECT cache_key FROM search_cache
                    ORDER BY created_at DESC
                    OFFSET ?
                )
                """,
                [limit],
            )

        try:
            self.db.write(_write)
        except Exception:
            return
