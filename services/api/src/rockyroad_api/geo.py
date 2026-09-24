from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import duckdb

from rockyroad_api.db import Database
from rockyroad_data.manifests import read_json
from rockyroad_data.paths import GEO_MANIFEST, PARQUET_DATASETS
from rockyroad_data.regions import RegionConfigError, load_regions, profile_bounds

logger = logging.getLogger(__name__)


def read_manifest(geo_dir: Path) -> dict[str, Any]:
    manifest_path = geo_dir / "manifest.json"
    if not manifest_path.exists():
        if GEO_MANIFEST.exists() and geo_dir == GEO_MANIFEST.parent:
            manifest_path = GEO_MANIFEST
        else:
            return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def extract_profile(osm_dir: Path) -> str | None:
    profile = read_json(osm_dir / "manifest.json").get("profile")
    return str(profile) if profile else None


def extract_bounds(osm_dir: Path) -> list[float] | None:
    manifest = read_json(osm_dir / "manifest.json")
    bounds = manifest.get("bounds")
    if isinstance(bounds, list) and len(bounds) == 4:
        try:
            west, south, east, north = (float(value) for value in bounds)
        except (TypeError, ValueError):
            pass
        else:
            if west < east and south < north:
                return [west, south, east, north]
    profile = extract_profile(osm_dir)
    if not profile:
        return None
    try:
        return profile_bounds(load_regions(), profile)
    except (OSError, RegionConfigError):
        return None


HOSTED_PROFILE = "canada-usa"
HOSTED_COVERAGE_HINT = "Stay inside Canada and the USA."
HOSTED_BOUNDS_FALLBACK = [-168.0, 24.0, -52.0, 83.5]


def hosted_bounds() -> list[float]:
    try:
        bounds = profile_bounds(load_regions(), HOSTED_PROFILE)
    except (OSError, RegionConfigError):
        return list(HOSTED_BOUNDS_FALLBACK)
    return bounds if bounds else list(HOSTED_BOUNDS_FALLBACK)


def extract_coverage_hint(profile: str | None, *, hosted: bool = False) -> str:
    if hosted:
        return HOSTED_COVERAGE_HINT
    if profile == "sample":
        return "With the sample profile, stay on Prince Edward Island."
    if profile:
        return f"Stay inside the {profile} extract."
    return "Stay inside the downloaded OSM extract."


def point_in_extract(lon: float, lat: float, bounds: list[float] | None) -> bool:
    if bounds is None or len(bounds) != 4:
        return True
    west, south, east, north = bounds
    return west <= lon <= east and south <= lat <= north


def current_geo_version(db: Database) -> str | None:
    row = db.conn.execute("SELECT version FROM geo_meta ORDER BY imported_at DESC LIMIT 1").fetchone()
    return str(row[0]) if row else None


def fts_index_exists(conn: Any) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM duckdb_functions() WHERE schema_name = 'fts_main_geo_features' "
            "AND function_name = 'match_bm25' LIMIT 1"
        ).fetchone()
    )


def _create_fts_index(conn: Any) -> None:
    conn.execute(
        """
        PRAGMA create_fts_index(
            'geo_features', 'id', 'name', 'search_text',
            stemmer='porter', stopwords='english', ignore='(\\.|[^a-z])+',
            strip_accents=1, lower=1, overwrite=1
        )
        """
    )


def _drop_fts_index(conn: Any) -> None:
    conn.execute("PRAGMA drop_fts_index('geo_features')")


def _rebuild_fts(conn: Any) -> bool:
    if fts_index_exists(conn):
        _drop_fts_index(conn)
    try:
        _create_fts_index(conn)
        return True
    except duckdb.Error as exc:
        logger.exception("Local search index creation failed; using slower fallback search")
        # A failed PRAGMA may leave tables without the match_bm25 macro.
        conn.execute("DROP SCHEMA IF EXISTS fts_main_geo_features CASCADE")
        if fts_index_exists(conn):
            raise RuntimeError("Partial local search index could not be removed") from exc
        return False


def import_geo_if_changed(db: Database) -> dict[str, Any]:
    geo_dir = db.settings.geo_dir
    manifest = read_manifest(geo_dir)
    version = str(manifest.get("version") or "")
    if not version:
        return {"imported": False, "reason": "missing-manifest"}
    current = current_geo_version(db)
    if current == version:
        if db.read(fts_index_exists):
            return {"imported": False, "reason": "unchanged", "version": version, "fts_ready": True}
        ready = db.read(_rebuild_fts)
        return {
            "imported": False,
            "reason": "index-rebuilt" if ready else "index-unavailable",
            "version": version,
            "fts_ready": ready,
        }

    missing = [name for name in PARQUET_DATASETS if not (geo_dir / f"{name}.parquet").exists()]
    if missing:
        return {"imported": False, "reason": "missing-parquet", "missing": missing}

    def _swap(conn: Any) -> dict[str, Any]:
        # A failure to inspect or remove the old index must roll back the data swap.
        if fts_index_exists(conn):
            _drop_fts_index(conn)
        conn.execute("DROP TABLE IF EXISTS geo_features_staging")
        conn.execute(
            """
            CREATE TABLE geo_features_staging AS
            SELECT * FROM geo_features LIMIT 0
            """
        )
        total = 0
        for dataset in PARQUET_DATASETS:
            path = (geo_dir / f"{dataset}.parquet").resolve()
            conn.execute(
                """
                INSERT INTO geo_features_staging
                SELECT
                    id,
                    ? AS dataset,
                    name,
                    normalized_name,
                    search_text,
                    feature_type,
                    lon,
                    lat,
                    population,
                    population_score,
                    importance,
                    type_prior,
                    admin_level
                FROM read_parquet(?)
                """,
                [dataset, str(path)],
            )
            count = conn.execute(
                "SELECT COUNT(*) FROM geo_features_staging WHERE dataset = ?",
                [dataset],
            ).fetchone()
            total += int(count[0]) if count else 0
        conn.execute("DELETE FROM geo_features")
        conn.execute("INSERT INTO geo_features SELECT * FROM geo_features_staging")
        conn.execute("DROP TABLE geo_features_staging")
        conn.execute("DELETE FROM geo_meta")
        conn.execute(
            "INSERT INTO geo_meta VALUES ('all', ?, now(), ?)",
            [version, total],
        )
        return {"imported": True, "version": version, "rows": total}

    # Hold the API connection lock across both stages so searches never observe stale FTS.
    with db._lock:
        result = db.write(_swap)
        result["fts_ready"] = db.read(_rebuild_fts)
        return result
