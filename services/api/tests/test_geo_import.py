from __future__ import annotations

import json

import duckdb
import polars as pl
import pytest
from fastapi.testclient import TestClient

from rockyroad_api import geo, search
from rockyroad_api.db import Database
from rockyroad_api.geo import import_geo_if_changed
from rockyroad_api.main import create_app
from rockyroad_api.models import Viewport
from rockyroad_api.search import search_places
from rockyroad_api.settings import Settings
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
    assert first["fts_ready"] is True
    second = import_geo_if_changed(db)
    assert second["imported"] is False
    results = search_places(db, "charlottetown", Viewport(west=-64, south=46, east=-62, north=47))
    assert results.results[0].name == "Charlottetown"


def test_fts_failure_degrades_search_and_same_version_retry_recovers(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    db = Database(settings)
    _write_geo(db, "v1")
    db.close()
    (settings.maps_dir / "north-america.pmtiles").write_bytes(b"map")
    (settings.routing_dir / "valhalla_tiles.tar").write_bytes(b"routing")
    original_create = geo._create_fts_index

    def fail_index(_conn: object) -> None:
        raise duckdb.Error("simulated FTS build failure")

    monkeypatch.setattr(geo, "_create_fts_index", fail_index)
    with TestClient(create_app(settings)) as client:
        health = client.get("/api/health").json()
        assert health["geo"] is True
        assert health["status"] == "degraded"
        assert "search index" in health["detail"].lower()
        assert client.get("/api/search", params={"q": "charlottetown"}).json()["results"][0]["name"] == "Charlottetown"
        assert client.post("/api/admin/import-geo").json()["fts_ready"] is False
        assert "simulated FTS build failure" in caplog.text

        monkeypatch.setattr(geo, "_create_fts_index", original_create)
        retried = client.post("/api/admin/import-geo").json()
        assert retried == {"imported": False, "reason": "index-rebuilt", "version": "v1", "fts_ready": True}
        assert client.get("/api/health").json()["status"] == "ok"


def test_partial_fts_index_is_removed_after_build_failure(db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_geo(db, "v1")
    original_create = geo._create_fts_index

    def fail_after_creation(conn: object) -> None:
        original_create(conn)
        raise duckdb.Error("failure after partial creation")

    monkeypatch.setattr(geo, "_create_fts_index", fail_after_creation)
    assert import_geo_if_changed(db)["fts_ready"] is False
    assert db.read(geo.fts_index_exists) is False
    assert search_places(db, "charlottetown").results[0].name == "Charlottetown"


def test_partial_fts_schema_without_macro_is_removed(db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_geo(db, "v1")
    original_create = geo._create_fts_index

    def fail_before_macro(conn: duckdb.DuckDBPyConnection) -> None:
        conn.execute("CREATE SCHEMA fts_main_geo_features")
        raise duckdb.Error("failure after partial creation")

    monkeypatch.setattr(geo, "_create_fts_index", fail_before_macro)
    assert import_geo_if_changed(db)["fts_ready"] is False
    assert db.read(geo.fts_index_exists) is False
    assert (
        db.conn.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = 'fts_main_geo_features'"
        ).fetchone()
        is None
    )
    monkeypatch.setattr(geo, "_create_fts_index", original_create)
    assert import_geo_if_changed(db)["fts_ready"] is True


def test_new_version_rebuilds_fts_and_failed_swap_keeps_previous_version(db: Database) -> None:
    _write_geo(db, "v1")
    assert import_geo_if_changed(db)["fts_ready"] is True
    _write_geo(db, "v2", "Summerside")
    (db.settings.geo_dir / "places.parquet").write_bytes(b"invalid parquet")
    with pytest.raises(duckdb.Error):
        import_geo_if_changed(db)
    assert geo.current_geo_version(db) == "v1"
    assert db.read(geo.fts_index_exists) is True
    assert search_places(db, "charlottetown").results[0].name == "Charlottetown"
    _write_geo(db, "v2", "Summerside")
    assert import_geo_if_changed(db)["fts_ready"] is True
    assert geo.current_geo_version(db) == "v2"
    assert search_places(db, "summerside").results[0].name == "Summerside"


def test_search_query_error_propagates_when_catalog_reports_index(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_geo(db, "v1")
    monkeypatch.setattr(search, "fts_index_exists", lambda _conn: True)
    with pytest.raises(duckdb.Error):
        search_places(db, "charlottetown")


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
