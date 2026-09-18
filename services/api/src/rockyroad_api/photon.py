from __future__ import annotations

import hashlib
import json
import math
from typing import Any, cast

import httpx

from rockyroad_api.db import Database
from rockyroad_api.models import PlaceResult, SearchResponse, Viewport
from rockyroad_api.search import SearchError
from rockyroad_api.settings import Settings

PHOTON_COUNTRIES = ("CA", "US")


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
        feature_type = str(raw_type or "place")
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
            )
        )
    return SearchResponse(query=query, results=results)


def _photon_name(properties: dict[str, Any]) -> str:
    name = str(properties.get("name") or "").strip()
    if name:
        return name
    parts = [str(properties.get("housenumber") or ""), str(properties.get("street") or "")]
    street = " ".join(part for part in parts if part)
    if street.strip():
        return street.strip()
    for key in ("city", "locality", "state", "country"):
        value = str(properties.get(key) or "").strip()
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
            return cached
        payload = self._request(cleaned, viewport)
        result = map_photon_features(payload, query=cleaned, limit=self.settings.max_search_results)
        self._store_cache(key, cleaned, result)
        return result

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
