from __future__ import annotations

from pathlib import Path

import pytest

from rockyroad_data.places import (
    OSMIUM_IMAGE,
    build_places,
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
