from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rockyroad_data.manifests import (
    artifact_record,
    file_sha256,
    read_json,
    utc_now,
    write_json_atomic,
)
from rockyroad_data.paths import (
    MERGED_PBF,
    OSM_MANIFEST,
    ROUTING_DIR,
    ROUTING_MANIFEST,
    ensure_data_dirs,
)
from rockyroad_data.process import require_executable, run_command

VALHALLA_CONFIG = {
    "mjolnir": {
        "tile_dir": "valhalla_tiles",
        "concurrency": 1,
    }
}


def write_valhalla_config(routing_dir: Path, tile_dir: Path) -> Path:
    config_path = routing_dir / "valhalla.json"
    config = {
        "mjolnir": {
            "tile_dir": str(tile_dir),
            "concurrency": 1,
        },
        "additional_data": {"elevation": ""},
        "loki": {"actions": ["locate", "route", "optimized_route", "trace_route", "trace_attributes"]},
        "thor": {"source_to_target_algorithm": "select_optimal"},
        "service_limits": {
            "auto": {"max_distance": 5000000.0, "max_locations": 50},
            "trace": {"max_distance": 200000.0, "max_shape": 16000},
        },
    }
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    _ = VALHALLA_CONFIG
    return config_path


def build_routing(pbf: Path | None = None, output_dir: Path | None = None) -> dict[str, Any]:
    ensure_data_dirs()
    source = pbf or MERGED_PBF
    if not source.exists():
        raise FileNotFoundError(f"OSM extract is missing: {source}. Run rockyroad-data update-osm first.")
    dest = output_dir or ROUTING_DIR
    dest.mkdir(parents=True, exist_ok=True)
    tile_dir = dest / "valhalla_tiles"
    config_path = write_valhalla_config(dest, tile_dir)
    builder = require_executable("valhalla_build_tiles")
    run_command([builder, "-c", str(config_path), str(source)])
    extract = require_executable("valhalla_build_extract")
    tar_path = dest / "valhalla_tiles.tar"
    run_command([extract, "-c", str(config_path), "-v"])
    osm_manifest = read_json(OSM_MANIFEST)
    version_source = tar_path if tar_path.exists() else tile_dir
    version = file_sha256(tar_path)[:16] if tar_path.exists() else utc_now().replace(":", "")
    manifest = {
        "created_at": utc_now(),
        "source_pbf": artifact_record(source),
        "osm_version": osm_manifest.get("version"),
        "config": artifact_record(config_path),
        "tiles": (
            artifact_record(version_source)
            if version_source.is_file()
            else {"path": str(tile_dir), "exists": tile_dir.exists()}
        ),
        "version": version,
    }
    write_json_atomic(ROUTING_MANIFEST, manifest)
    return manifest
