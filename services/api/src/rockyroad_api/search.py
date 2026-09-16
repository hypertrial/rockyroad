from __future__ import annotations

import math
import uuid
from typing import Any

from rockyroad_api.db import Database
from rockyroad_api.models import PlaceResult, RecentSearchOut, SearchResponse, Viewport


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _proximity_score(distance_km: float) -> float:
    if distance_km <= 0:
        return 1.0
    return max(0.0, 1.0 - min(distance_km, 1500.0) / 1500.0)


def rank_rows(rows: list[dict[str, Any]], viewport: Viewport | None) -> list[dict[str, Any]]:
    if not rows:
        return []
    bm25_values = [float(row.get("bm25") or 0.0) for row in rows]
    max_bm25 = max(bm25_values) or 1.0
    center = viewport.center if viewport else None
    ranked: list[dict[str, Any]] = []
    for row in rows:
        bm25_norm = float(row.get("bm25") or 0.0) / max_bm25
        distance_km = 0.0
        if center is not None:
            distance_km = _haversine_km(center[0], center[1], float(row["lon"]), float(row["lat"]))
        proximity = _proximity_score(distance_km) if center else 0.5
        score = (
            0.45 * bm25_norm
            + 0.20 * float(row["importance"])
            + 0.15 * float(row["population_score"])
            + 0.10 * float(row["type_prior"])
            + 0.10 * proximity
        )
        ranked.append({**row, "score": round(score, 6), "distance_km": distance_km})
    ranked.sort(key=lambda item: (-item["score"], item["name"]))
    return ranked


def search_places(
    db: Database,
    query: str,
    viewport: Viewport | None = None,
    limit: int | None = None,
) -> SearchResponse:
    cleaned = " ".join(query.split())
    if not cleaned:
        return SearchResponse(query=query, results=[])
    max_results = limit or db.settings.max_search_results
    params: list[Any] = [cleaned, max_results * 5]

    def _query(conn: Any) -> list[Any]:
        try:
            return conn.execute(
                """
                SELECT
                    id,
                    dataset,
                    name,
                    feature_type,
                    lon,
                    lat,
                    population,
                    population_score,
                    importance,
                    type_prior,
                    fts_main_geo_features.match_bm25(id, ?) AS bm25
                FROM geo_features
                QUALIFY bm25 IS NOT NULL
                ORDER BY bm25 DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        except Exception:
            like = f"%{cleaned.casefold()}%"
            return conn.execute(
                """
                SELECT
                    id,
                    dataset,
                    name,
                    feature_type,
                    lon,
                    lat,
                    population,
                    population_score,
                    importance,
                    type_prior,
                    1.0 AS bm25
                FROM geo_features
                WHERE (normalized_name LIKE ? OR search_text LIKE ?)
                LIMIT ?
                """,
                [like, like, max_results * 5],
            ).fetchall()

    rows = db.read(_query)

    mapped = [
        {
            "id": row[0],
            "dataset": row[1],
            "name": row[2],
            "feature_type": row[3],
            "lon": row[4],
            "lat": row[5],
            "population": row[6],
            "population_score": row[7],
            "importance": row[8],
            "type_prior": row[9],
            "bm25": row[10],
        }
        for row in rows
    ]
    ranked = rank_rows(mapped, viewport)[:max_results]
    results = [
        PlaceResult(
            id=item["id"],
            name=item["name"],
            feature_type=item["feature_type"],
            dataset=item["dataset"],
            lon=item["lon"],
            lat=item["lat"],
            score=item["score"],
            population=item["population"],
        )
        for item in ranked
    ]
    return SearchResponse(query=cleaned, results=results)


def record_recent_search(db: Database, query: str, result_place_id: str | None = None) -> None:
    cleaned = " ".join(query.split())
    if not cleaned:
        return

    def _write(conn: Any) -> None:
        conn.execute(
            "INSERT INTO recent_searches VALUES (?, ?, ?, now())",
            [str(uuid.uuid4()), cleaned, result_place_id],
        )
        conn.execute(
            """
            DELETE FROM recent_searches
            WHERE id IN (
                SELECT id FROM recent_searches
                ORDER BY created_at DESC
                OFFSET ?
            )
            """,
            [db.settings.recent_search_limit],
        )

    db.write(_write)


def list_recent_searches(db: Database) -> list[RecentSearchOut]:
    rows = db.conn.execute(
        """
        SELECT id, query, result_place_id, created_at
        FROM recent_searches
        ORDER BY created_at DESC
        """
    ).fetchall()
    return [RecentSearchOut(id=row[0], query=row[1], result_place_id=row[2], created_at=row[3]) for row in rows]
