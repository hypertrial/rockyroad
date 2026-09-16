from __future__ import annotations

import json
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import polars as pl

from rockyroad_data.manifests import (
    artifact_record,
    file_sha256,
    read_json,
    utc_now,
    write_json_atomic,
)
from rockyroad_data.paths import (
    GEO_DIR,
    GEO_MANIFEST,
    MERGED_PBF,
    OSM_MANIFEST,
    PARQUET_DATASETS,
    ensure_data_dirs,
)
from rockyroad_data.process import require_executable, run_command
from rockyroad_data.regions import load_regions

OSMIUM_FILTERS = [
    "n/place",
    "nwr/leisure=park",
    "nwr/leisure=nature_reserve",
    "nwr/boundary=national_park",
    "nwr/tourism=camp_site",
    "nwr/tourism=caravan_site",
    "nwr/amenity=fuel",
    "nwr/tourism=attraction",
    "nwr/tourism=museum",
    "nwr/tourism=viewpoint",
    "nwr/historic",
    "wr/boundary=administrative",
]


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.casefold().split())


def log_population(raw: Any) -> float:
    try:
        population = float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0
    if population <= 0:
        return 0.0
    return min(1.0, math.log10(population + 1) / 7.0)


def feature_type(props: dict[str, Any]) -> str:
    place = props.get("place")
    if place:
        return str(place)
    tourism = props.get("tourism")
    if tourism == "camp_site" or tourism == "caravan_site":
        return "campsite"
    if tourism in {"attraction", "museum", "viewpoint"}:
        return str(tourism)
    if props.get("amenity") == "fuel":
        return "fuel"
    leisure = props.get("leisure")
    if leisure == "park":
        return "park"
    if leisure == "nature_reserve":
        return "nature_reserve"
    if props.get("boundary") == "national_park":
        return "national_park"
    if props.get("historic"):
        return "historic"
    if props.get("boundary") == "administrative":
        return "boundary"
    return "other"


def dataset_for(feature_kind: str) -> str:
    if feature_kind in {"city", "town", "village", "hamlet", "suburb", "neighbourhood", "isolated_dwelling"}:
        return "places"
    if feature_kind in {"park", "national_park", "nature_reserve"}:
        return "parks"
    if feature_kind == "campsite":
        return "campsites"
    if feature_kind == "fuel":
        return "fuel"
    if feature_kind in {"attraction", "museum", "viewpoint", "historic"}:
        return "attractions"
    if feature_kind == "boundary":
        return "boundaries"
    return "places"


def centroid(geometry: dict[str, Any] | None) -> tuple[float, float] | None:
    if not geometry:
        return None
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")
    if geom_type == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return float(coords[0]), float(coords[1])
    ring: list[Any] | None = None
    if geom_type == "Polygon" and isinstance(coords, list) and coords:
        ring = coords[0] if isinstance(coords[0], list) else None
    elif geom_type == "MultiPolygon" and isinstance(coords, list) and coords:
        first = coords[0]
        ring = first[0] if isinstance(first, list) and first else None
    if not ring:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for pair in ring:
        if isinstance(pair, list) and len(pair) >= 2:
            xs.append(float(pair[0]))
            ys.append(float(pair[1]))
    if not xs:
        return None
    return sum(xs) / len(xs), sum(ys) / len(ys)


def aliases(props: dict[str, Any]) -> str:
    values: list[str] = []
    for key, value in props.items():
        if not isinstance(value, str):
            continue
        if key in {"name", "alt_name", "short_name", "official_name", "loc_name"} or key.startswith("name:"):
            normalized = normalize_name(value)
            if normalized and normalized not in values:
                values.append(normalized)
    return " ".join(values)


def importance_for(feature_kind: str, priors: dict[str, float], population_score: float) -> float:
    prior = float(priors.get(feature_kind, priors.get("other", 0.2)))
    return min(1.0, 0.65 * prior + 0.35 * population_score)


def iter_geojsonseq(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def rows_from_export(export_path: Path, priors: dict[str, float]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in PARQUET_DATASETS}
    for feature in iter_geojsonseq(export_path):
        props = feature.get("properties") or {}
        if not isinstance(props, dict):
            continue
        name = props.get("name")
        if not name:
            continue
        kind = feature_type(props)
        dataset = dataset_for(kind)
        if dataset == "boundaries":
            admin_level = str(props.get("admin_level") or "")
            if admin_level not in {"2", "4", "6"}:
                continue
        point = centroid(feature.get("geometry"))
        if point is None:
            continue
        lon, lat = point
        population_score = log_population(props.get("population"))
        search_text = aliases(props) or normalize_name(str(name))
        osm_id = str(props.get("@id") or props.get("id") or f"{dataset}:{name}:{lon}:{lat}")
        buckets[dataset].append(
            {
                "id": osm_id,
                "name": str(name),
                "normalized_name": normalize_name(str(name)),
                "search_text": search_text,
                "feature_type": kind,
                "lon": lon,
                "lat": lat,
                "population": _as_int(props.get("population")),
                "population_score": population_score,
                "importance": importance_for(kind, priors, population_score),
                "type_prior": float(priors.get(kind, priors.get("other", 0.2))),
                "admin_level": props.get("admin_level"),
            }
        )
    return buckets


def _as_int(raw: Any) -> int | None:
    try:
        return int(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None


SCHEMA = {
    "id": pl.Utf8,
    "name": pl.Utf8,
    "normalized_name": pl.Utf8,
    "search_text": pl.Utf8,
    "feature_type": pl.Utf8,
    "lon": pl.Float64,
    "lat": pl.Float64,
    "population": pl.Int64,
    "population_score": pl.Float64,
    "importance": pl.Float64,
    "type_prior": pl.Float64,
    "admin_level": pl.Utf8,
}


def write_parquet_datasets(buckets: dict[str, list[dict[str, Any]]], output_dir: Path) -> dict[str, Path]:
    written: dict[str, Path] = {}
    for name in PARQUET_DATASETS:
        frame = pl.DataFrame(buckets.get(name, []), schema=SCHEMA)
        destination = output_dir / f"{name}.parquet"
        tmp = destination.with_suffix(".parquet.tmp")
        frame.write_parquet(tmp)
        tmp.replace(destination)
        written[name] = destination
    return written


def export_filtered_features(pbf: Path, export_path: Path) -> None:
    osmium = require_executable("osmium")
    filtered = export_path.with_suffix(".filtered.osm.pbf")
    if filtered.exists():
        filtered.unlink()
    run_command([osmium, "tags-filter", str(pbf), *OSMIUM_FILTERS, "-o", str(filtered)])
    if export_path.exists():
        export_path.unlink()
    run_command(
        [
            osmium,
            "export",
            "-f",
            "geojsonseq",
            "--geometry-types=point,polygon",
            str(filtered),
            "-o",
            str(export_path),
        ]
    )
    filtered.unlink(missing_ok=True)


def build_places(pbf: Path | None = None, output_dir: Path | None = None) -> dict[str, Any]:
    ensure_data_dirs()
    source = pbf or MERGED_PBF
    if not source.exists():
        raise FileNotFoundError(f"OSM extract is missing: {source}. Run rockyroad-data update-osm first.")
    dest = output_dir or GEO_DIR
    dest.mkdir(parents=True, exist_ok=True)
    config = load_regions()
    priors = {str(key): float(value) for key, value in (config.get("feature_priors") or {}).items()}
    export_path = dest / "features.geojsonseq"
    export_filtered_features(source, export_path)
    buckets = rows_from_export(export_path, priors)
    written = write_parquet_datasets(buckets, dest)
    export_path.unlink(missing_ok=True)
    osm_manifest = read_json(OSM_MANIFEST)
    manifest = {
        "created_at": utc_now(),
        "source_pbf": artifact_record(source),
        "osm_version": osm_manifest.get("version"),
        "datasets": {name: artifact_record(path, {"rows": len(buckets[name])}) for name, path in written.items()},
        "version": file_sha256(written["places"])[:16],
    }
    for name in PARQUET_DATASETS:
        manifest["datasets"][name]["rows"] = len(buckets[name])
    write_json_atomic(GEO_MANIFEST, manifest)
    return manifest
