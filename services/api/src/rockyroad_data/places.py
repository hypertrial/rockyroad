from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import duckdb
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
    MERGED_PBF,
    OSM_MANIFEST,
    PARQUET_DATASETS,
    ensure_data_dirs,
)
from rockyroad_data.process import ToolError, docker_stage_dir, require_executable, run_command
from rockyroad_data.regions import load_regions

OSMIUM_IMAGE = os.environ.get("ROCKYROAD_OSMIUM_IMAGE", "iboates/osmium:1.19.0")

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


def _ring_points(raw: Any) -> list[tuple[float, float]]:
    if not isinstance(raw, list):
        return []
    points = [(float(item[0]), float(item[1])) for item in raw if isinstance(item, list) and len(item) >= 2]
    return points if len(points) >= 3 else []


def _scanline_point(rings: list[list[tuple[float, float]]]) -> tuple[float, float] | None:
    ys = [y for ring in rings for _, y in ring]
    south, north = min(ys), max(ys)
    if south == north:
        return None
    candidates = [south + (north - south) * (index + 0.5) / 32 for index in range(32)]
    best: tuple[float, tuple[float, float]] | None = None
    for y in candidates:
        intersections: list[float] = []
        for ring in rings:
            for (x1, y1), (x2, y2) in zip(ring, [*ring[1:], ring[0]], strict=True):
                if (y1 > y) != (y2 > y):
                    intersections.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        intersections.sort()
        for left, right in zip(intersections[::2], intersections[1::2], strict=False):
            point = ((left + right) / 2, y)
            width = right - left
            if width > 0 and (best is None or width > best[0]):
                best = (width, point)
    return best[1] if best else None


def _polygon_area(ring: list[tuple[float, float]]) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, [*ring[1:], ring[0]], strict=True))) / 2


def centroid(geometry: dict[str, Any] | None) -> tuple[float, float] | None:
    if not geometry:
        return None
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")
    if geom_type == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return float(coords[0]), float(coords[1])
    polygons: list[Any] = []
    if geom_type == "Polygon" and isinstance(coords, list):
        polygons = [coords]
    elif geom_type == "MultiPolygon" and isinstance(coords, list):
        polygons = coords
    parsed = [[_ring_points(ring) for ring in polygon] for polygon in polygons if isinstance(polygon, list)]
    valid = [[ring for ring in polygon if ring] for polygon in parsed]
    valid = [polygon for polygon in valid if polygon]
    if not valid:
        return None
    rings = max(valid, key=lambda polygon: _polygon_area(polygon[0]))
    return _scanline_point(rings) or rings[0][0]


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


def iter_export_rows(export_path: Path, priors: dict[str, float]) -> Iterator[tuple[str, dict[str, Any]]]:
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
        osm_id = str(
            feature.get("id")
            or props.get("@id")
            or props.get("id")
            or f"{dataset}:{normalize_name(str(name))}:{lon:.6f}:{lat:.6f}"
        )
        yield (
            dataset,
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
            },
        )


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


def build_parquet_datasets(export_path: Path, priors: dict[str, float], output_dir: Path) -> dict[str, int]:
    """Stage bounded row batches, then select deterministic winners with spillable DuckDB."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".places-build-", dir=output_dir) as temporary:
        stage = Path(temporary)
        chunks = {name: [] for name in PARQUET_DATASETS}
        batches: dict[str, list[dict[str, Any]]] = {name: [] for name in PARQUET_DATASETS}
        sequence = {name: 0 for name in PARQUET_DATASETS}

        def flush(name: str) -> None:
            if not batches[name]:
                return
            path = stage / f"{name}-{len(chunks[name]):05d}.parquet"
            pl.DataFrame(batches[name], schema={**SCHEMA, "_sequence": pl.Int64}).write_parquet(path)
            chunks[name].append(path)
            batches[name] = []

        for name, row in iter_export_rows(export_path, priors):
            batches[name].append({**row, "_sequence": sequence[name]})
            sequence[name] += 1
            if len(batches[name]) == 10_000:
                flush(name)
        for name in PARQUET_DATASETS:
            flush(name)

        connection = duckdb.connect(
            ":memory:", config={"memory_limit": "512MB", "temp_directory": str(stage / "spill")}
        )
        counts: dict[str, int] = {}
        try:
            columns = ", ".join(f'"{column}"' for column in SCHEMA)
            for name in PARQUET_DATASETS:
                staged = stage / f"{name}.parquet"
                if chunks[name]:
                    target = str(staged).replace("'", "''")
                    connection.execute(
                        f"""
                        COPY (
                            SELECT {columns} FROM (
                                SELECT *,
                                    MIN(_sequence) OVER (PARTITION BY id) AS _first,
                                    ROW_NUMBER() OVER (
                                        PARTITION BY id ORDER BY importance DESC, _sequence ASC
                                    ) AS _winner
                                FROM read_parquet(?)
                            ) WHERE _winner = 1 ORDER BY _first
                        ) TO '{target}' (FORMAT PARQUET)
                        """,
                        [[str(path) for path in chunks[name]]],
                    )
                else:
                    pl.DataFrame([], schema=SCHEMA).write_parquet(staged)
                frame = pl.scan_parquet(staged)
                if frame.collect_schema() != pl.Schema(SCHEMA):
                    raise ValueError(f"Unexpected schema in staged {name} dataset")
                counts[name] = int(frame.select(pl.len()).collect().item())
        finally:
            connection.close()

        for name in PARQUET_DATASETS:
            (stage / f"{name}.parquet").replace(output_dir / f"{name}.parquet")
        return counts


def _osmium_args(osmium: str, filtered: Path, export_path: Path, source: Path) -> tuple[list[str], list[str]]:
    return (
        [osmium, "tags-filter", str(source), *OSMIUM_FILTERS, "-o", str(filtered)],
        [
            osmium,
            "export",
            "-f",
            "geojsonseq",
            "-u",
            "type_id",
            "--geometry-types=point,polygon",
            str(filtered),
            "-o",
            str(export_path),
        ],
    )


def _export_filtered_host(pbf: Path, export_path: Path) -> None:
    osmium = require_executable("osmium")
    filtered = export_path.with_suffix(".filtered.osm.pbf")
    if filtered.exists():
        filtered.unlink()
    if export_path.exists():
        export_path.unlink()
    filter_args, export_args = _osmium_args(osmium, filtered, export_path, pbf)
    try:
        run_command(filter_args)
        run_command(export_args)
    finally:
        filtered.unlink(missing_ok=True)


def _export_filtered_docker(pbf: Path, export_path: Path) -> None:
    docker = require_executable("docker")
    work = docker_stage_dir(export_path.parent, env_var="ROCKYROAD_OSMIUM_FILES", cache_name="osmium")
    staged = work / "input.osm.pbf"
    filtered = work / "features.filtered.osm.pbf"
    exported = work / "features.geojsonseq"
    shutil.copy2(pbf, staged)
    try:
        for extra in (filtered, exported):
            extra.unlink(missing_ok=True)
        run_command(
            [
                docker,
                "run",
                "--rm",
                "-v",
                f"{work}:/data",
                OSMIUM_IMAGE,
                "tags-filter",
                "/data/input.osm.pbf",
                *OSMIUM_FILTERS,
                "-o",
                "/data/features.filtered.osm.pbf",
            ]
        )
        run_command(
            [
                docker,
                "run",
                "--rm",
                "-v",
                f"{work}:/data",
                OSMIUM_IMAGE,
                "export",
                "-f",
                "geojsonseq",
                "-u",
                "type_id",
                "--geometry-types=point,polygon",
                "/data/features.filtered.osm.pbf",
                "-o",
                "/data/features.geojsonseq",
            ]
        )
        if exported.resolve() != export_path.resolve():
            export_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(exported, export_path)
    finally:
        staged.unlink(missing_ok=True)
        filtered.unlink(missing_ok=True)
        if exported.resolve() != export_path.resolve():
            exported.unlink(missing_ok=True)


def export_filtered_features(pbf: Path, export_path: Path) -> None:
    if shutil.which("osmium"):
        _export_filtered_host(pbf, export_path)
        return
    try:
        require_executable("docker")
    except ToolError as exc:
        raise ToolError(
            "osmium is not installed. Install osmium or Docker, then rerun rockyroad-data build-places."
        ) from exc
    _export_filtered_docker(pbf, export_path)


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
    try:
        export_filtered_features(source, export_path)
        counts = build_parquet_datasets(export_path, priors, dest)
    finally:
        export_path.unlink(missing_ok=True)
    written = {name: dest / f"{name}.parquet" for name in PARQUET_DATASETS}
    osm_manifest = read_json(OSM_MANIFEST)
    manifest = {
        "created_at": utc_now(),
        "source_pbf": artifact_record(source),
        "osm_version": osm_manifest.get("version"),
        "datasets": {name: artifact_record(path, {"rows": counts[name]}) for name, path in written.items()},
        "version": hashlib.sha256(
            "".join(file_sha256(written[name]) for name in PARQUET_DATASETS).encode("utf-8")
        ).hexdigest()[:16],
    }
    write_json_atomic(dest / "manifest.json", manifest)
    return manifest
