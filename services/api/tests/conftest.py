from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rockyroad_api.db import Database
from rockyroad_api.main import create_app
from rockyroad_api.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    geo_dir = tmp_path / "geo"
    geo_dir.mkdir()
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    routing_dir = tmp_path / "routing"
    routing_dir.mkdir()
    osm_dir = tmp_path / "osm"
    osm_dir.mkdir()
    return Settings(
        duckdb_path=tmp_path / "rockyroad.duckdb",
        geo_dir=geo_dir,
        maps_dir=maps_dir,
        osm_dir=osm_dir,
        routing_dir=routing_dir,
        valhalla_url="http://valhalla.test",
        provider_mode="local",
    )


@pytest.fixture
def db(settings: Settings) -> Iterator[Database]:
    database = Database(settings)
    yield database
    database.close()


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
