from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
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
from rockyroad_data.process import ToolError, docker_can_bind, require_executable, run_command

VALHALLA_IMAGE = os.environ.get(
    "ROCKYROAD_VALHALLA_IMAGE",
    "ghcr.io/valhalla/valhalla-scripted:latest",
)
MANAGED_ROUTING_ARTIFACTS = {"manifest.json", "valhalla.json", "valhalla_tiles", "valhalla_tiles.tar"}


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


def docker_files_dir(dest: Path) -> Path:
    override = os.environ.get("ROCKYROAD_VALHALLA_FILES")
    if override:
        return Path(override).expanduser().resolve()
    resolved = dest.resolve()
    if docker_can_bind(resolved):
        return resolved
    return (Path.home() / ".cache" / "rockyroad" / "valhalla").resolve()


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


def _build_routing_docker(source: Path, files_dir: Path) -> None:
    docker = require_executable("docker")
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


def _staging_dir(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f".{target.name}.build-", dir=target.parent))


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def _publish_directories(replacements: list[tuple[Path, Path]]) -> None:
    published: list[tuple[Path, Path, bool]] = []
    try:
        for staged, target in replacements:
            backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}"
            had_previous = target.exists()
            if had_previous:
                target.replace(backup)
                try:
                    _require_managed_target(backup)
                except Exception:
                    backup.replace(target)
                    raise
            try:
                staged.replace(target)
            except Exception:
                if had_previous:
                    backup.replace(target)
                raise
            published.append((target, backup, had_previous))
    except Exception:
        for target, backup, had_previous in reversed(published):
            _remove_path(target)
            if had_previous:
                backup.replace(target)
        raise
    else:
        for _target, backup, had_previous in published:
            if had_previous:
                _remove_path(backup)


def _artifact_record_at(source: Path, published: Path) -> dict[str, Any]:
    record = artifact_record(source)
    record["path"] = str(published)
    return record


def _validate_routing_build(build_dir: Path) -> None:
    config_path = build_dir / "valhalla.json"
    tar_path = build_dir / "valhalla_tiles.tar"
    tile_dir = build_dir / "valhalla_tiles"
    has_tiles = tar_path.is_file() and tar_path.stat().st_size > 0
    if tile_dir.is_dir():
        has_tiles = has_tiles or any(path.is_file() and path.stat().st_size > 0 for path in tile_dir.rglob("*"))
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        config = None
    mjolnir = config.get("mjolnir") if isinstance(config, dict) else None
    has_tile_reference = isinstance(mjolnir, dict) and any(
        isinstance(mjolnir.get(key), str) and bool(mjolnir[key].strip()) for key in ("tile_dir", "tile_extract")
    )
    if not has_tile_reference or not has_tiles:
        raise ToolError("Valhalla build did not produce a config and non-empty routing tiles")


def _require_managed_target(target: Path) -> None:
    if not target.exists():
        return
    if not target.is_dir():
        raise ToolError(f"routing output target is not a directory: {target}")
    unmanaged = sorted(path.name for path in target.iterdir() if path.name not in MANAGED_ROUTING_ARTIFACTS)
    if unmanaged:
        names = ", ".join(unmanaged)
        raise ToolError(f"routing output target contains unmanaged entries ({names}): {target}")


def _routing_manifest(source: Path, build_dir: Path, dest: Path, docker_files: Path) -> dict[str, Any]:
    osm_manifest = read_json(OSM_MANIFEST)
    config_path = build_dir / "valhalla.json"
    tar_path = build_dir / "valhalla_tiles.tar"
    tile_dir = build_dir / "valhalla_tiles"
    version_source = tar_path if tar_path.exists() else tile_dir
    version = file_sha256(tar_path)[:16] if tar_path.exists() else utc_now().replace(":", "")
    return {
        "created_at": utc_now(),
        "source_pbf": artifact_record(source),
        "osm_version": osm_manifest.get("version"),
        "config": _artifact_record_at(config_path, dest / "valhalla.json"),
        "tiles": (
            _artifact_record_at(version_source, dest / "valhalla_tiles.tar")
            if version_source.is_file()
            else {"path": str(dest / "valhalla_tiles"), "exists": tile_dir.exists()}
        ),
        "docker_files": str(docker_files),
        "version": version,
    }


def build_routing(pbf: Path | None = None, output_dir: Path | None = None) -> dict[str, Any]:
    ensure_data_dirs()
    source = pbf or MERGED_PBF
    if not source.exists():
        raise FileNotFoundError(f"OSM extract is missing: {source}. Run rockyroad-data update-osm first.")
    dest = (output_dir or ROUTING_DIR).resolve()
    host_tools = _host_valhalla_tools()
    if host_tools is None:
        try:
            require_executable("docker")
        except ToolError as exc:
            raise ToolError(
                "Valhalla tools are not installed. Install valhalla_build_tiles or Docker, "
                "then rerun rockyroad-data build-routing."
            ) from exc
        docker_files = docker_files_dir(dest)
    else:
        docker_files = dest
    if docker_files != dest and (docker_files.is_relative_to(dest) or dest.is_relative_to(docker_files)):
        raise ToolError("ROCKYROAD_VALHALLA_FILES must not be nested inside the routing output directory")
    _require_managed_target(dest)
    if docker_files != dest:
        _require_managed_target(docker_files)

    build_stage = _staging_dir(dest if host_tools is not None else docker_files)
    mirror_stage: Path | None = None
    try:
        if host_tools is not None:
            config_path = write_valhalla_config(build_stage, build_stage / "valhalla_tiles")
            _build_routing_host(source, config_path)
            write_valhalla_config(build_stage, dest / "valhalla_tiles")
        else:
            _build_routing_docker(source, build_stage)
        _validate_routing_build(build_stage)

        manifest_source = build_stage
        replacements = [(build_stage, dest)]
        if docker_files != dest:
            mirror_stage = _staging_dir(dest)
            _copy_build_outputs(build_stage, mirror_stage, skip={source.name})
            manifest_source = mirror_stage
            replacements = [(build_stage, docker_files), (mirror_stage, dest)]
        manifest = _routing_manifest(source, manifest_source, dest, docker_files)
        write_json_atomic(manifest_source / "manifest.json", manifest)
        _publish_directories(replacements)
        return manifest
    finally:
        _remove_path(build_stage)
        if mirror_stage is not None:
            _remove_path(mirror_stage)
