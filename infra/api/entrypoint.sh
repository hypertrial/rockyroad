#!/bin/sh
set -eu

legacy_path="${ROCKYROAD_LEGACY_DUCKDB_PATH:-/data/rockyroad.duckdb}"
target_path="${ROCKYROAD_DUCKDB_PATH:-/state/rockyroad.duckdb}"

if [ ! -e "$target_path" ] && [ -f "$legacy_path" ]; then
  target_dir="$(dirname "$target_path")"
  mkdir -p "$target_dir"
  cp "$legacy_path" "$target_path.migrating"
  if [ -f "$legacy_path.wal" ]; then
    cp "$legacy_path.wal" "$target_path.wal.migrating"
    mv "$target_path.wal.migrating" "$target_path.wal"
  fi
  mv "$target_path.migrating" "$target_path"
  echo "Migrated the legacy RockyRoad database into persistent Compose state."
fi

exec "$@"
