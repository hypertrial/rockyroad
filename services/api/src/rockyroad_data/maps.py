from __future__ import annotations

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
    MAPS_DIR,
    MERGED_PBF,
    OSM_MANIFEST,
    PLANETILER_JAR,
    TOOLS_DIR,
    ensure_data_dirs,
)
from rockyroad_data.process import require_executable, run_command

PLANETILER_URL = "https://github.com/onthegomap/planetiler/releases/download/v0.9.0/planetiler.jar"
PMTILES_NAME = "north-america.pmtiles"


def require_planetiler(destination: Path = PLANETILER_JAR) -> Path:
    if destination.exists() and destination.stat().st_size > 1_000_000:
        return destination
    raise FileNotFoundError(
        f"Planetiler jar is missing at {destination}. "
        f"Place planetiler.jar from {PLANETILER_URL} into tools/ before running build-map. "
        "build-map is offline and will not download it."
    )


def build_map(
    pbf: Path | None = None,
    output_dir: Path | None = None,
    jar: Path | None = None,
) -> dict[str, Any]:
    ensure_data_dirs()
    source = pbf or MERGED_PBF
    if not source.exists():
        raise FileNotFoundError(f"OSM extract is missing: {source}. Run rockyroad-data update-osm first.")
    dest_dir = output_dir or MAPS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    output = dest_dir / PMTILES_NAME
    java = require_executable("java")
    planetiler = require_planetiler(jar or PLANETILER_JAR)
    tmp = output.with_suffix(".tmp.pmtiles")
    if tmp.exists():
        tmp.unlink()
    run_command(
        [
            java,
            "-Xmx4g",
            "-jar",
            str(planetiler),
            "--osm-path",
            str(source),
            "--output",
            str(tmp),
            "--force",
        ],
        cwd=TOOLS_DIR,
    )
    tmp.replace(output)
    osm_manifest = read_json(OSM_MANIFEST)
    manifest = {
        "created_at": utc_now(),
        "source_pbf": artifact_record(source),
        "osm_version": osm_manifest.get("version"),
        "pmtiles": artifact_record(output),
        "version": file_sha256(output)[:16],
    }
    write_json_atomic(dest_dir / "manifest.json", manifest)
    return manifest
