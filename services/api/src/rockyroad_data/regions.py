from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from rockyroad_data.paths import REGIONS_PATH


class RegionConfigError(ValueError):
    pass


def load_regions(path: Path | None = None) -> dict[str, Any]:
    config_path = path or REGIONS_PATH
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RegionConfigError("regions.yaml must be a mapping")
    return payload


def allowed_extracts(config: dict[str, Any]) -> set[str]:
    extracts: set[str] = set()
    profiles = config.get("profiles")
    if not isinstance(profiles, dict):
        raise RegionConfigError("regions.yaml is missing profiles")
    for profile in profiles.values():
        if not isinstance(profile, dict):
            continue
        items = profile.get("extracts", [])
        if not isinstance(items, list):
            raise RegionConfigError("profile extracts must be a list")
        extracts.update(str(item) for item in items)
    return extracts


def profile_bounds(config: dict[str, Any], profile_name: str | None) -> list[float] | None:
    name = profile_name or str(config.get("default_profile") or "sample")
    profiles = config.get("profiles")
    if not isinstance(profiles, dict):
        return None
    profile = profiles.get(name)
    if not isinstance(profile, dict):
        return None
    bounds = profile.get("bounds")
    if not isinstance(bounds, list) or len(bounds) != 4:
        return None
    try:
        west, south, east, north = (float(value) for value in bounds)
    except (TypeError, ValueError):
        return None
    if west >= east or south >= north:
        return None
    return [west, south, east, north]


def resolve_profile(config: dict[str, Any], profile_name: str | None) -> tuple[str, list[str]]:
    name = profile_name or str(config.get("default_profile") or "sample")
    profiles = config.get("profiles")
    if not isinstance(profiles, dict) or name not in profiles:
        raise RegionConfigError(f"unknown region profile: {name}")
    profile = profiles[name]
    extracts = profile.get("extracts")
    if not isinstance(extracts, list) or not extracts:
        raise RegionConfigError(f"profile {name} has no extracts")
    return name, [str(item) for item in extracts]


def geofabrik_urls(config: dict[str, Any], extract: str) -> tuple[str, str]:
    allowed = allowed_extracts(config)
    if extract not in allowed:
        raise RegionConfigError(f"extract is not allow-listed: {extract}")
    if ".." in extract or extract.startswith("/") or extract.startswith("\\"):
        raise RegionConfigError(f"invalid extract path: {extract}")
    base = str(config.get("geofabrik_base") or "https://download.geofabrik.de").rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RegionConfigError("geofabrik_base must be an http(s) URL")
    pbf = f"{base}/{extract}-latest.osm.pbf"
    md5 = f"{pbf}.md5"
    return pbf, md5
