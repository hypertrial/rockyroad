from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import duckdb

from rockyroad_api.db import MIGRATIONS_DIR, Database, _sql_statements
from rockyroad_api.settings import Settings
from rockyroad_api.trips import get_trip, list_saved_places


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        duckdb_path=tmp_path / "rockyroad.duckdb",
        geo_dir=tmp_path / "geo",
        maps_dir=tmp_path / "maps",
        osm_dir=tmp_path / "osm",
        routing_dir=tmp_path / "routing",
        provider_mode="local",
    )


def test_place_region_migration_reads_legacy_rows_as_null(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(settings.duckdb_path))
    conn.execute(
        """
        CREATE TABLE schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL
        )
        """
    )
    for version in ("001_init", "002_search_cache"):
        sql = (MIGRATIONS_DIR / f"{version}.sql").read_text(encoding="utf-8")
        for statement in _sql_statements(sql):
            conn.execute(statement)
        conn.execute("INSERT INTO schema_migrations VALUES (?, now())", [version])
    trip_id = uuid4()
    stop_id = uuid4()
    conn.execute("INSERT INTO trips VALUES (?, ?, now(), now())", [str(trip_id), "Legacy"])
    conn.execute(
        "INSERT INTO trip_stops VALUES (?, ?, ?, ?, ?, ?, ?, now())",
        [str(stop_id), str(trip_id), 0, "Charlottetown", -63.131, 46.238, "place-a"],
    )
    conn.execute(
        """
        INSERT INTO trip_settings VALUES (?, FALSE, FALSE, FALSE, 'auto', FALSE, 0, now())
        """,
        [str(trip_id)],
    )
    place_id = uuid4()
    conn.execute(
        "INSERT INTO saved_places VALUES (?, ?, ?, ?, ?, ?, now())",
        [str(place_id), "Charlottetown", -63.131, 46.238, "place-a", None],
    )
    conn.close()

    db = Database(settings)
    stop_columns = {row[1] for row in db.conn.execute("PRAGMA table_info('trip_stops')").fetchall()}
    place_columns = {row[1] for row in db.conn.execute("PRAGMA table_info('saved_places')").fetchall()}
    assert "region" in stop_columns
    assert "region" in place_columns
    trip = get_trip(db, trip_id)
    assert trip is not None
    assert trip.stops[0].name == "Charlottetown"
    assert trip.stops[0].region is None
    saved = list_saved_places(db)
    assert saved[0].id == place_id
    assert saved[0].region is None
    db.close()
