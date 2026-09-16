from __future__ import annotations

import json

import polars as pl

from rockyroad_api.db import Database
from rockyroad_api.geo import import_geo_if_changed
from rockyroad_api.models import Viewport
from rockyroad_api.search import search_places
from rockyroad_data.paths import PARQUET_DATASETS
from rockyroad_data.places import SCHEMA


def _write_geo(db: Database, version: str, extra_name: str = "Charlottetown") -> None:
    rows = [
        {
            "id": f"place:{extra_name}",
            "name": extra_name,
            "normalized_name": extra_name.casefold(),
            "search_text": extra_name.casefold(),
            "feature_type": "city",
            "lon": -63.131,
            "lat": 46.238,
            "population": 38000,
            "population_score": 0.6,
            "importance": 0.85,
            "type_prior": 1.0,
            "admin_level": None,
        }
    ]
    for name in PARQUET_DATASETS:
        frame = pl.DataFrame(rows if name == "places" else [], schema=SCHEMA)
        frame.write_parquet(db.settings.geo_dir / f"{name}.parquet")
    (db.settings.geo_dir / "manifest.json").write_text(
        json.dumps({"version": version}),
        encoding="utf-8",
    )


def test_import_is_atomic_and_searchable(db: Database) -> None:
    _write_geo(db, "v1")
    first = import_geo_if_changed(db)
    assert first["imported"] is True
    second = import_geo_if_changed(db)
    assert second["imported"] is False
    results = search_places(db, "charlottetown", Viewport(west=-64, south=46, east=-62, north=47))
    assert results.results[0].name == "Charlottetown"


def test_search_returns_places_outside_viewport(db: Database) -> None:
    _write_geo(db, "v1")
    import_geo_if_changed(db)
    results = search_places(
        db,
        "charlottetown",
        Viewport(west=-123.3, south=49.1, east=-123.0, north=49.4),
    )
    assert results.results[0].name == "Charlottetown"


def test_failed_import_keeps_previous_dataset(db: Database) -> None:
    _write_geo(db, "v1")
    import_geo_if_changed(db)
    (db.settings.geo_dir / "places.parquet").unlink()
    (db.settings.geo_dir / "manifest.json").write_text(json.dumps({"version": "v2"}), encoding="utf-8")
    result = import_geo_if_changed(db)
    assert result["imported"] is False
    results = search_places(db, "charlottetown")
    assert results.results[0].name == "Charlottetown"
