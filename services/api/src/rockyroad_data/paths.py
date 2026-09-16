from __future__ import annotations

import os
from pathlib import Path


def find_repo_root() -> Path:
    env = os.environ.get("ROCKYROAD_REPO_ROOT")
    if env:
        return Path(env).resolve()
    search = [Path.cwd(), *Path.cwd().parents, Path(__file__).resolve(), *Path(__file__).resolve().parents]
    for candidate in search:
        if (candidate / "pyproject.toml").exists() and (candidate / "config" / "regions.yaml").exists():
            return candidate
    return Path.cwd()


REPO_ROOT = find_repo_root()
CONFIG_DIR = REPO_ROOT / "config"
REGIONS_PATH = CONFIG_DIR / "regions.yaml"
DATA_DIR = REPO_ROOT / "data"
OSM_DIR = DATA_DIR / "osm"
GEO_DIR = DATA_DIR / "geo"
MAPS_DIR = DATA_DIR / "maps"
ROUTING_DIR = DATA_DIR / "routing" / "valhalla"
TOOLS_DIR = REPO_ROOT / "tools"

MERGED_PBF = OSM_DIR / "north-america.osm.pbf"
PMTILES_PATH = MAPS_DIR / "north-america.pmtiles"
PLANETILER_JAR = TOOLS_DIR / "planetiler.jar"
GEO_MANIFEST = GEO_DIR / "manifest.json"
OSM_MANIFEST = OSM_DIR / "manifest.json"
ROUTING_MANIFEST = ROUTING_DIR / "manifest.json"
MAP_MANIFEST = MAPS_DIR / "manifest.json"

PARQUET_DATASETS = (
    "places",
    "parks",
    "campsites",
    "fuel",
    "attractions",
    "boundaries",
)


def ensure_data_dirs() -> None:
    for path in (OSM_DIR, GEO_DIR, MAPS_DIR, ROUTING_DIR, TOOLS_DIR):
        path.mkdir(parents=True, exist_ok=True)
