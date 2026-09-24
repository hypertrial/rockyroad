from __future__ import annotations

import json
from types import SimpleNamespace

import duckdb
import polars as pl
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from rockyroad_api.db import Database
from rockyroad_api.geo import current_geo_version, fts_ready, import_geo_if_changed
from rockyroad_api.main import create_app
from rockyroad_api.models import Viewport
from rockyroad_api.routers.health import health
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
    assert db.read(fts_ready)
    second = import_geo_if_changed(db)
    assert second["imported"] is False
    results = search_places(db, "charlottetown", Viewport(west=-64, south=46, east=-62, north=47))
    assert results.results[0].name == "Charlottetown"


def test_index_failure_degrades_search_and_same_version_retries(db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_geo(db, "v1")
    original_write = db.write

    class FailingConnection:
        def __init__(self, conn: object) -> None:
            self.conn = conn

        def execute(self, sql: str, *args: object) -> object:
            if "create_fts_index" in sql:
                raise duckdb.Error("injected index failure")
            return self.conn.execute(sql, *args)  # type: ignore[attr-defined]

    monkeypatch.setattr(db, "write", lambda fn: original_write(lambda conn: fn(FailingConnection(conn))))
    first = import_geo_if_changed(db)
    assert first["imported"] is True and first["fts_ready"] is False
    assert not db.read(fts_ready)
    response = health(Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace(db=db))}))
    assert response.geo is True and response.status == "degraded"
    assert "slower fallback" in (response.detail or "")
    assert search_places(db, "charlottetown").results[0].name == "Charlottetown"

    monkeypatch.setattr(db, "write", original_write)
    retry = import_geo_if_changed(db)
    assert retry == {"imported": False, "reason": "unchanged", "version": "v1", "fts_ready": True}
    assert db.read(fts_ready)
    assert search_places(db, "charlottetown").results[0].name == "Charlottetown"


def test_indexed_query_errors_propagate(db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_geo(db, "v1")
    assert import_geo_if_changed(db)["fts_ready"]
    original_read = db.read

    class FailingConnection:
        def __init__(self, conn: object) -> None:
            self.conn = conn

        def execute(self, sql: str, *args: object) -> object:
            if "match_bm25(id" in sql:
                raise RuntimeError("unrelated query failure")
            return self.conn.execute(sql, *args)  # type: ignore[attr-defined]

    monkeypatch.setattr(db, "read", lambda fn: original_read(lambda conn: fn(FailingConnection(conn))))
    with pytest.raises(RuntimeError, match="unrelated query failure"):
        search_places(db, "charlottetown")


def test_startup_and_admin_retry_unchanged_index(settings: Settings) -> None:
    db = Database(settings)
    try:
        _write_geo(db, "v1")
        assert import_geo_if_changed(db)["fts_ready"]
        db.write(lambda conn: conn.execute("PRAGMA drop_fts_index('geo_features')"))
        assert not db.read(fts_ready)
    finally:
        db.close()

    app = create_app(settings)
    with TestClient(app) as client:
        assert app.state.db.read(fts_ready)
        app.state.db.write(lambda conn: conn.execute("PRAGMA drop_fts_index('geo_features')"))
        response = client.post("/api/admin/import-geo")
        assert response.status_code == 200
        assert response.json()["fts_ready"] is True
        assert response.json()["imported"] is False


def test_retry_removes_partial_fts_schema_before_rebuilding(db: Database) -> None:
    _write_geo(db, "v1")
    db.write(lambda conn: conn.execute("CREATE SCHEMA fts_main_geo_features"))
    assert not db.read(fts_ready)
    result = import_geo_if_changed(db)
    assert result["fts_ready"] is True
    assert search_places(db, "charlottetown").results[0].name == "Charlottetown"


def test_invalid_parquet_rolls_back_data_and_index(db: Database) -> None:
    _write_geo(db, "v1")
    assert import_geo_if_changed(db)["fts_ready"]
    _write_geo(db, "v2", "Changed")
    (db.settings.geo_dir / "parks.parquet").write_bytes(b"invalid parquet")
    with pytest.raises(duckdb.Error):
        import_geo_if_changed(db)
    assert current_geo_version(db) == "v1"
    assert db.read(fts_ready)
    assert search_places(db, "charlottetown").results[0].name == "Charlottetown"


def test_new_version_replaces_existing_index_and_rows(db: Database) -> None:
    _write_geo(db, "v1")
    assert import_geo_if_changed(db)["fts_ready"]
    _write_geo(db, "v2", "Summerside")
    result = import_geo_if_changed(db)
    assert result["imported"] is True and result["fts_ready"] is True
    assert current_geo_version(db) == "v2"
    assert db.read(fts_ready)
    assert [place.name for place in search_places(db, "summerside").results] == ["Summerside"]
    assert search_places(db, "charlottetown").results == []


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
