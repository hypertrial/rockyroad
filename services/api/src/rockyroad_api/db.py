from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import duckdb

from rockyroad_api.settings import Settings

T = TypeVar("T")
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class _MaterializedResult:
    """Snapshot of a DuckDB result fetched while the connection lock is held."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def fetchall(self) -> list[Any]:
        return self._rows

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None


class _LockedConnection:
    """Serialize every DuckDB execute+fetch pair on the shared connection."""

    def __init__(self, conn: duckdb.DuckDBPyConnection, lock: threading.RLock) -> None:
        self._conn = conn
        self._lock = lock

    def execute(self, *args: Any, **kwargs: Any) -> _MaterializedResult:
        with self._lock:
            return _MaterializedResult(list(self._conn.execute(*args, **kwargs).fetchall()))

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._raw = duckdb.connect(str(settings.duckdb_path))
        self.conn = _LockedConnection(self._raw, self._lock)
        self._load_extensions()
        self.migrate()

    def _load_extensions(self) -> None:
        with self._lock:
            if self.settings.extensions_dir is not None:
                self._raw.execute(f"SET extension_directory = '{self.settings.extensions_dir}'")
            for extension in ("spatial", "fts"):
                try:
                    self._raw.execute(f"LOAD {extension}")
                except duckdb.Error:
                    self._raw.execute(f"INSTALL {extension}")
                    self._raw.execute(f"LOAD {extension}")

    def migrate(self) -> None:
        with self._lock:
            self._raw.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL
                )
                """
            )
            applied = {row[0] for row in self._raw.execute("SELECT version FROM schema_migrations").fetchall()}
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                version = path.stem
                if version in applied:
                    continue
                sql = path.read_text(encoding="utf-8")
                self._raw.execute("BEGIN")
                try:
                    for statement in _sql_statements(sql):
                        self._raw.execute(statement)
                    self._raw.execute(
                        "INSERT INTO schema_migrations VALUES (?, now())",
                        [version],
                    )
                    self._raw.execute("COMMIT")
                except Exception:
                    self._raw.execute("ROLLBACK")
                    raise

    def read(self, fn: Callable[[duckdb.DuckDBPyConnection], T]) -> T:
        with self._lock:
            return fn(self._raw)

    def write(self, fn: Callable[[duckdb.DuckDBPyConnection], T]) -> T:
        with self._lock:
            self._raw.execute("BEGIN")
            try:
                result = fn(self._raw)
                self._raw.execute("COMMIT")
                return result
            except Exception:
                self._raw.execute("ROLLBACK")
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
