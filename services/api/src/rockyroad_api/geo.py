from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from typing import Any

from rockyroad_api.db import Database
from rockyroad_data.paths import GEO_MANIFEST, PARQUET_DATASETS


def read_manifest(geo_dir: Path) -> dict[str, Any]:
    manifest_path = geo_dir / "manifest.json"
    if not manifest_path.exists():
        if GEO_MANIFEST.exists() and geo_dir == GEO_MANIFEST.parent:
            manifest_path = GEO_MANIFEST
        else:
            return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def current_geo_version(db: Database) -> str | None:
    row = db.conn.execute("SELECT version FROM geo_meta ORDER BY imported_at DESC LIMIT 1").fetchone()
    return str(row[0]) if row else None


def import_geo_if_changed(db: Database) -> dict[str, Any]:
    geo_dir = db.settings.geo_dir
    manifest = read_manifest(geo_dir)
    version = str(manifest.get("version") or "")
    if not version:
        return {"imported": False, "reason": "missing-manifest"}
    current = current_geo_version(db)
    if current == version:
        return {"imported": False, "reason": "unchanged", "version": version}

    missing = [name for name in PARQUET_DATASETS if not (geo_dir / f"{name}.parquet").exists()]
    if missing:
        return {"imported": False, "reason": "missing-parquet", "missing": missing}

    def _swap(conn: Any) -> dict[str, Any]:
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
        with suppress(Exception):
            conn.execute("PRAGMA drop_fts_index('geo_features')")
        with suppress(Exception):
            conn.execute(
                """
                PRAGMA create_fts_index(
                    'geo_features',
                    'id',
                    'name',
                    'search_text',
                    stemmer='porter',
                    stopwords='english',
                    ignore='(\\.|[^a-z])+',
                    strip_accents=1,
                    lower=1,
                    overwrite=1
                )
                """
            )
        return {"imported": True, "version": version, "rows": total}

    return db.write(_swap)
