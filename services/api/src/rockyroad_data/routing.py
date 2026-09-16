from __future__ import annotations

import json
import os
import shutil
import sys
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
    ensure_data_dirs,
)
from rockyroad_data.process import ToolError, require_executable, run_command

VALHALLA_IMAGE = os.environ.get(
    "ROCKYROAD_VALHALLA_IMAGE",
    "ghcr.io/valhalla/valhalla-scripted:latest",
)


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
    return config_path


def docker_can_bind(path: Path) -> bool:
    resolved = path.resolve()
    if " " in str(resolved):
        return False
    try:
        resolved.relative_to(Path.home().resolve())
        return True
    except ValueError:
        return sys.platform.startswith("linux")


def docker_files_dir(dest: Path) -> Path:
    override = os.environ.get("ROCKYROAD_VALHALLA_FILES")
    if override:
        path = Path(override).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()
    resolved = dest.resolve()
    if docker_can_bind(resolved):
        return resolved
    path = Path.home() / ".cache" / "rockyroad" / "valhalla"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _host_valhalla_tools() -> tuple[str, str] | None:
    builder = shutil.which("valhalla_build_tiles")
    extract = shutil.which("valhalla_build_extract")
    if builder and extract:
        return builder, extract
    return None


def _build_routing_host(source: Path, config_path: Path) -> None:
    tools = _host_valhalla_tools()
    if tools is None:
        raise ToolError("Valhalla host tools are not on PATH")
    builder, extract = tools
    run_command([builder, "-c", str(config_path), str(source)])
    run_command([extract, "-c", str(config_path), "-v"])


def _copy_build_outputs(src: Path, dest: Path, skip: set[str]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in skip:
            continue
        target = dest / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        elif item.is_file():
            shutil.copy2(item, target)


def _build_routing_docker(source: Path, dest: Path) -> Path:
    docker = require_executable("docker")
    dest.mkdir(parents=True, exist_ok=True)
    files_dir = docker_files_dir(dest)
    files_dir.mkdir(parents=True, exist_ok=True)
    staged = files_dir / source.name
    copied = source.resolve() != staged.resolve()
    if copied:
        shutil.copy2(source, staged)
    try:
        run_command(
            [
                docker,
                "run",
                "--rm",
                "-e",
                "serve_tiles=False",
                "-e",
                "use_tiles_ignore_pbf=False",
                "-e",
                "force_rebuild=True",
                "-e",
                "build_elevation=False",
                "-e",
                "build_admins=False",
                "-e",
                "build_time_zones=False",
                "-e",
                "build_tar=True",
                "-e",
                "use_default_speeds_config=False",
                "-e",
                "tile_urls=",
                "-v",
                f"{files_dir}:/custom_files",
                VALHALLA_IMAGE,
            ]
        )
    finally:
        if copied:
            staged.unlink(missing_ok=True)
    if files_dir != dest.resolve():
        _copy_build_outputs(files_dir, dest, skip={source.name})
    return files_dir


def build_routing(pbf: Path | None = None, output_dir: Path | None = None) -> dict[str, Any]:
    ensure_data_dirs()
    source = pbf or MERGED_PBF
    if not source.exists():
        raise FileNotFoundError(f"OSM extract is missing: {source}. Run rockyroad-data update-osm first.")
    dest = output_dir or ROUTING_DIR
    dest.mkdir(parents=True, exist_ok=True)
    tile_dir = dest / "valhalla_tiles"
    config_path = dest / "valhalla.json"
    docker_files = dest
    if _host_valhalla_tools() is not None:
        write_valhalla_config(dest, tile_dir)
        _build_routing_host(source, config_path)
    else:
        try:
            require_executable("docker")
        except ToolError as exc:
            raise ToolError(
                "Valhalla tools are not installed. Install valhalla_build_tiles or Docker, "
                "then rerun rockyroad-data build-routing."
            ) from exc
        docker_files = _build_routing_docker(source, dest)
    osm_manifest = read_json(OSM_MANIFEST)
    tar_path = dest / "valhalla_tiles.tar"
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
        "docker_files": str(docker_files),
        "version": version,
    }
    write_json_atomic(dest / "manifest.json", manifest)
    return manifest
