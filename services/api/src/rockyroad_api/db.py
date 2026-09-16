from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import duckdb

from rockyroad_api.settings import Settings

T = TypeVar("T")
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_write_lock = threading.RLock()


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(settings.duckdb_path))
        self._load_extensions()
        self.migrate()

    def _load_extensions(self) -> None:
        if self.settings.extensions_dir is not None:
            self.conn.execute(f"SET extension_directory = '{self.settings.extensions_dir}'")
        for extension in ("spatial", "fts"):
            try:
                self.conn.execute(f"LOAD {extension}")
            except duckdb.Error:
                self.conn.execute(f"INSTALL {extension}")
                self.conn.execute(f"LOAD {extension}")

    def migrate(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL
            )
            """
        )
        applied = {row[0] for row in self.conn.execute("SELECT version FROM schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.stem
            if version in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            self.conn.execute("BEGIN")
            try:
                for statement in _sql_statements(sql):
                    self.conn.execute(statement)
                self.conn.execute(
                    "INSERT INTO schema_migrations VALUES (?, now())",
                    [version],
                )
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

    def write(self, fn: Callable[[duckdb.DuckDBPyConnection], T]) -> T:
        with _write_lock:
            self.conn.execute("BEGIN")
            try:
                result = fn(self.conn)
                self.conn.execute("COMMIT")
                return result
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        self.conn.close()


def _sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(buffer))
            buffer = []
    if buffer:
        statements.append("\n".join(buffer))
    return statements
