from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx

from rockyroad_data.manifests import artifact_record, file_sha256, utc_now, write_json_atomic
from rockyroad_data.paths import MERGED_PBF, OSM_DIR, OSM_MANIFEST, ensure_data_dirs
from rockyroad_data.process import require_executable, run_command
from rockyroad_data.regions import geofabrik_urls, load_regions, resolve_profile


def extract_filename(extract: str) -> str:
    return extract.replace("/", "__") + "-latest.osm.pbf"


def download_file(url: str, destination: Path, *, etag: str | None = None) -> dict[str, Any]:
    headers: dict[str, str] = {}
    if etag and destination.exists():
        headers["If-None-Match"] = etag
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".part")
    with (
        httpx.Client(follow_redirects=True, timeout=120.0) as client,
        client.stream("GET", url, headers=headers) as response,
    ):
        if response.status_code == 304 and destination.exists():
            return {"changed": False, "etag": etag, "path": str(destination)}
        response.raise_for_status()
        with tmp.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)
        new_etag = response.headers.get("etag")
    tmp.replace(destination)
    return {"changed": True, "etag": new_etag, "path": str(destination)}


def verify_md5(pbf_path: Path, md5_text: str) -> None:
    expected = md5_text.split()[0].strip().lower()
    md5 = hashlib.md5(usedforsecurity=False)
    with pbf_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
    actual = md5.hexdigest()
    if actual != expected:
        raise ValueError(f"MD5 mismatch for {pbf_path.name}: expected {expected}, got {actual}")


def merge_extracts(pbf_paths: list[Path], output: Path) -> None:
    osmium = require_executable("osmium")
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".tmp.osm.pbf")
    if tmp.exists():
        tmp.unlink()
    if len(pbf_paths) == 1:
        tmp.write_bytes(pbf_paths[0].read_bytes())
    else:
        run_command([osmium, "merge", *[str(path) for path in pbf_paths], "-o", str(tmp)])
    tmp.replace(output)


def update_osm(profile_name: str | None = None, regions_path: Path | None = None) -> dict[str, Any]:
    ensure_data_dirs()
    config = load_regions(regions_path)
    name, extracts = resolve_profile(config, profile_name)
    previous = {}
    if OSM_MANIFEST.exists():
        previous = __import__("json").loads(OSM_MANIFEST.read_text(encoding="utf-8"))
    previous_files = {item["extract"]: item for item in previous.get("extracts", []) if isinstance(item, dict)}

    extract_records: list[dict[str, Any]] = []
    local_paths: list[Path] = []
    for extract in extracts:
        pbf_url, md5_url = geofabrik_urls(config, extract)
        local = OSM_DIR / extract_filename(extract)
        prior = previous_files.get(extract, {})
        download = download_file(pbf_url, local, etag=prior.get("etag"))
        md5_path = local.with_suffix(local.suffix + ".md5")
        download_file(md5_url, md5_path)
        verify_md5(local, md5_path.read_text(encoding="utf-8"))
        record = artifact_record(
            local,
            {
                "extract": extract,
                "url": pbf_url,
                "etag": download.get("etag"),
                "changed": download.get("changed"),
            },
        )
        extract_records.append(record)
        local_paths.append(local)

    merge_extracts(local_paths, MERGED_PBF)
    manifest = {
        "created_at": utc_now(),
        "profile": name,
        "extracts": extract_records,
        "merged": artifact_record(MERGED_PBF),
        "version": file_sha256(MERGED_PBF)[:16],
    }
    write_json_atomic(OSM_MANIFEST, manifest)
    return manifest
