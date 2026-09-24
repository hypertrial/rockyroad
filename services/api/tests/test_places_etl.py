from __future__ import annotations

import json
import math
import time
from pathlib import Path

import polars as pl
import pytest

from rockyroad_data.paths import PARQUET_DATASETS
from rockyroad_data.places import (
    OSMIUM_IMAGE,
    SCHEMA,
    build_parquet_datasets,
    build_places,
    centroid,
    dataset_for,
    feature_type,
    normalize_name,
    rows_from_export,
)
from rockyroad_data.process import ToolError


def test_feature_classification() -> None:
    assert feature_type({"place": "town"}) == "town"
    assert feature_type({"tourism": "camp_site"}) == "campsite"
    assert dataset_for("fuel") == "fuel"
    assert normalize_name("  Charlottetown ") == "charlottetown"


def test_polygon_representative_points_stay_inside_concave_and_holed_shapes() -> None:
    concave = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [4, 0], [4, 4], [3, 4], [3, 1], [1, 1], [1, 4], [0, 4], [0, 0]]],
    }
    holed = {
        "type": "Polygon",
        "coordinates": [
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
        ],
    }
    concave_point = centroid(concave)
    holed_point = centroid(holed)
    assert concave_point is not None
    assert concave_point[1] <= 1 or concave_point[0] <= 1 or concave_point[0] >= 3
    assert holed_point is not None
    assert 0 <= holed_point[0] <= 10 and 0 <= holed_point[1] <= 10
    assert not (4 < holed_point[0] < 6 and 4 < holed_point[1] < 6)


def test_multipolygon_uses_the_largest_polygon() -> None:
    point = centroid(
        {
            "type": "MultiPolygon",
            "coordinates": [
                [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                [[[10, 10], [20, 10], [20, 20], [10, 20], [10, 10]]],
            ],
        }
    )
    assert point is not None
    assert 10 <= point[0] <= 20 and 10 <= point[1] <= 20


def test_polygon_representative_point_is_bounded_for_large_boundaries() -> None:
    ring = []
    for index in range(800):
        angle = 2 * math.pi * index / 800
        radius = 10 if index % 2 == 0 else 4
        ring.append([radius * math.cos(angle), radius * math.sin(angle)])
    ring.append(ring[0])
    started = time.monotonic()
    point = centroid({"type": "Polygon", "coordinates": [ring]})
    assert time.monotonic() - started < 2
    assert point is not None


def test_rows_from_geojsonseq(tmp_path) -> None:
    export = tmp_path / "features.geojsonseq"
    export.write_text(
        '{"type":"Feature","properties":{"name":"Charlottetown","place":"city","population":"38000","@id":"node/1"},"geometry":{"type":"Point","coordinates":[-63.13,46.24]}}\n',
        encoding="utf-8",
    )
    buckets = rows_from_export(export, {"city": 1.0, "other": 0.2})
    assert buckets["places"][0]["name"] == "Charlottetown"
    assert buckets["places"][0]["importance"] > 0.5


def test_rows_from_export_uses_feature_id_and_dedupes(tmp_path: Path) -> None:
    export = tmp_path / "features.geojsonseq"
    export.write_text(
        '{"type":"Feature","id":"node/1","properties":{"name":"Keppoch","place":"suburb"},'
        '"geometry":{"type":"Point","coordinates":[-63.108,46.202]}}\n'
        '{"type":"Feature","properties":{"name":"Keppoch","place":"suburb"},'
        '"geometry":{"type":"Point","coordinates":[-63.108,46.202]}}\n'
        '{"type":"Feature","properties":{"name":"Keppoch","place":"hamlet"},'
        '"geometry":{"type":"Point","coordinates":[-63.108,46.202]}}\n',
        encoding="utf-8",
    )
    buckets = rows_from_export(export, {"suburb": 0.4, "hamlet": 0.2, "other": 0.2})
    assert [row["id"] for row in buckets["places"]] == ["node/1", "places:keppoch:-63.108000:46.202000"]


def test_staged_build_matches_reference_across_batch_boundary(tmp_path: Path) -> None:
    export = tmp_path / "features.geojsonseq"
    with export.open("w", encoding="utf-8") as handle:
        for index in range(10_001):
            feature = {
                "type": "Feature",
                "id": f"node/{index}",
                "properties": {"name": f"Place {index}", "place": "city"},
                "geometry": {"type": "Point", "coordinates": [-63.0, 46.0]},
            }
            handle.write(json.dumps(feature) + "\n")
        for name, kind in [("Place 0 updated", "town"), ("Place 1 tie", "city")]:
            duplicate = {
                "type": "Feature",
                "id": "node/0" if kind == "town" else "node/1",
                "properties": {"name": name, "place": kind},
                "geometry": {"type": "Point", "coordinates": [-63.0, 46.0]},
            }
            handle.write(json.dumps(duplicate) + "\n")
    priors = {"city": 0.5, "town": 0.9, "other": 0.2}
    expected = rows_from_export(export, priors)
    output = tmp_path / "output"
    counts = build_parquet_datasets(export, priors, output)
    for name in PARQUET_DATASETS:
        frame = pl.read_parquet(output / f"{name}.parquet")
        assert frame.schema == SCHEMA
        assert frame.to_dicts() == pl.DataFrame(expected[name], schema=SCHEMA).to_dicts()
        assert counts[name] == len(expected[name])
    assert not list(output.glob(".places-build-*"))


def test_staged_build_cleans_up_after_malformed_input(tmp_path: Path) -> None:
    export = tmp_path / "features.geojsonseq"
    feature = {
        "type": "Feature",
        "id": "node/1",
        "properties": {"name": "Town", "place": "city"},
        "geometry": {"type": "Point", "coordinates": [-63.0, 46.0]},
    }
    with export.open("w", encoding="utf-8") as handle:
        for _ in range(10_000):
            handle.write(json.dumps(feature) + "\n")
        handle.write("{invalid json}\n")
    output = tmp_path / "output"
    output.mkdir()
    previous = output / "places.parquet"
    previous.write_bytes(b"previous")
    with pytest.raises(json.JSONDecodeError):
        build_parquet_datasets(export, {}, output)
    assert previous.read_bytes() == b"previous"
    assert not list(output.glob(".places-build-*"))


def test_failed_host_export_removes_partial_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rockyroad_data.places import _export_filtered_host

    export = tmp_path / "features.geojsonseq"
    filtered = export.with_suffix(".filtered.osm.pbf")

    def fail_export(_args: list[str]) -> None:
        filtered.write_bytes(b"partial")
        export.write_bytes(b"partial")
        raise ToolError("osmium failed")

    monkeypatch.setattr("rockyroad_data.places.require_executable", lambda _name: "osmium")
    monkeypatch.setattr("rockyroad_data.places.run_command", fail_export)
    with pytest.raises(ToolError):
        _export_filtered_host(tmp_path / "source.pbf", export)
    assert not filtered.exists()


def test_build_places_removes_partial_export_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.pbf"
    source.write_bytes(b"pbf")
    output = tmp_path / "geo"

    def fail_export(_source: Path, export: Path) -> None:
        export.write_bytes(b"partial")
        raise ToolError("osmium failed")

    monkeypatch.setattr("rockyroad_data.places.ensure_data_dirs", lambda: None)
    monkeypatch.setattr("rockyroad_data.places.export_filtered_features", fail_export)
    with pytest.raises(ToolError):
        build_places(pbf=source, output_dir=output)
    assert not (output / "features.geojsonseq").exists()


def test_build_places_uses_docker_when_osmium_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "north-america.osm.pbf"
    source.write_bytes(b"pbf")
    dest = tmp_path / "geo"
    bind = tmp_path / "bind"
    commands: list[list[str]] = []
    monkeypatch.setenv("ROCKYROAD_OSMIUM_FILES", str(bind))

    def fake_run(args: list[str], **_kwargs: object) -> None:
        commands.append(list(args))
        exported = bind / "features.geojsonseq"
        exported.write_text(
            '{"type":"Feature","properties":{"name":"Charlottetown","place":"city","@id":"node/1"},'
            '"geometry":{"type":"Point","coordinates":[-63.13,46.24]}}\n',
            encoding="utf-8",
        )

    monkeypatch.setattr("rockyroad_data.places.shutil.which", lambda _name: None)
    monkeypatch.setattr("rockyroad_data.places.require_executable", lambda _name: "docker")
    monkeypatch.setattr("rockyroad_data.places.run_command", fake_run)
    monkeypatch.setattr("rockyroad_data.places.ensure_data_dirs", lambda: None)

    manifest = build_places(pbf=source, output_dir=dest)
    assert commands[0][0] == "docker"
    assert OSMIUM_IMAGE in commands[0]
    assert "tags-filter" in commands[0]
    assert "export" in commands[1]
    assert commands[1][commands[1].index("-u") + 1] == "type_id"
    assert (dest / "places.parquet").exists()
    assert (dest / "manifest.json").exists()
    assert manifest["datasets"]["places"]["rows"] == 1


def test_build_places_prefers_host_osmium(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "north-america.osm.pbf"
    source.write_bytes(b"pbf")
    dest = tmp_path / "geo"
    commands: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs: object) -> None:
        commands.append(list(args))
        export = dest / "features.geojsonseq"
        dest.mkdir(parents=True, exist_ok=True)
        export.write_text(
            '{"type":"Feature","id":"node/1","properties":{"name":"Charlottetown","place":"city"},'
            '"geometry":{"type":"Point","coordinates":[-63.13,46.24]}}\n',
            encoding="utf-8",
        )

    def fake_which(name: str) -> str | None:
        return "/usr/bin/osmium" if name == "osmium" else None

    monkeypatch.setattr("rockyroad_data.places.shutil.which", fake_which)
    monkeypatch.setattr("rockyroad_data.places.require_executable", lambda name: "/usr/bin/osmium")
    monkeypatch.setattr("rockyroad_data.places.run_command", fake_run)
    monkeypatch.setattr("rockyroad_data.places.ensure_data_dirs", lambda: None)

    build_places(pbf=source, output_dir=dest)
    assert commands[0][0] == "/usr/bin/osmium"
    assert all(args[0] != "docker" for args in commands)


def test_build_places_version_covers_non_place_datasets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.osm.pbf"
    source.write_bytes(b"pbf")
    dest = tmp_path / "geo"
    park_lon = -63.2

    def fake_export(_source: Path, output: Path) -> None:
        output.write_text(
            '{"type":"Feature","id":"node/1","properties":{"name":"Town","place":"city"},'
            '"geometry":{"type":"Point","coordinates":[-63.13,46.24]}}\n'
            f'{{"type":"Feature","id":"way/2","properties":{{"name":"Park","leisure":"park"}},'
            f'"geometry":{{"type":"Point","coordinates":[{park_lon},46.3]}}}}\n',
            encoding="utf-8",
        )

    monkeypatch.setattr("rockyroad_data.places.ensure_data_dirs", lambda: None)
    monkeypatch.setattr("rockyroad_data.places.export_filtered_features", fake_export)
    first = build_places(pbf=source, output_dir=dest)
    park_lon = -63.4
    second = build_places(pbf=source, output_dir=dest)
    assert first["datasets"]["places"]["sha256"] == second["datasets"]["places"]["sha256"]
    assert first["datasets"]["parks"]["sha256"] != second["datasets"]["parks"]["sha256"]
    assert first["version"] != second["version"]


def test_build_places_requires_osmium_or_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "north-america.osm.pbf"
    source.write_bytes(b"pbf")
    monkeypatch.setattr("rockyroad_data.places.shutil.which", lambda _name: None)
    monkeypatch.setattr(
        "rockyroad_data.places.require_executable",
        lambda _name: (_ for _ in ()).throw(ToolError("missing")),
    )
    monkeypatch.setattr("rockyroad_data.places.ensure_data_dirs", lambda: None)
    with pytest.raises(ToolError, match="Docker"):
        build_places(pbf=source, output_dir=tmp_path / "geo")
