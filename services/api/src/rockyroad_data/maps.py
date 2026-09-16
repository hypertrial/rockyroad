from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from rockyroad_data.manifests import (
    artifact_record,
    file_sha256,
    read_json,
    utc_now,
    write_json_atomic,
)
from rockyroad_data.paths import (
    MAP_MANIFEST,
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


def download_planetiler(destination: Path = PLANETILER_JAR) -> Path:
    if destination.exists() and destination.stat().st_size > 1_000_000:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(".part")
    with (
        httpx.Client(follow_redirects=True, timeout=180.0) as client,
        client.stream("GET", PLANETILER_URL) as response,
    ):
        response.raise_for_status()
        with tmp.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)
    tmp.replace(destination)
    return destination


def build_map(pbf: Path | None = None, output_dir: Path | None = None) -> dict[str, Any]:
    ensure_data_dirs()
    source = pbf or MERGED_PBF
    if not source.exists():
        raise FileNotFoundError(f"OSM extract is missing: {source}. Run rockyroad-data update-osm first.")
    dest_dir = output_dir or MAPS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    output = dest_dir / PMTILES_NAME
    java = require_executable("java")
    jar = download_planetiler()
    tmp = output.with_suffix(".tmp.pmtiles")
    if tmp.exists():
        tmp.unlink()
    run_command(
        [
            java,
            "-Xmx4g",
            "-jar",
            str(jar),
            "--osm-path",
            str(source),
            "--output",
            str(tmp),
            "--download",
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
    write_json_atomic(MAP_MANIFEST, manifest)
    return manifest
