from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from rockyroad_data.cli import app

runner = CliRunner()


def test_build_routing_prints_docker_bind_hint(monkeypatch) -> None:
    monkeypatch.setattr(
        "rockyroad_data.cli.build_routing",
        lambda: {"version": "abc", "docker_files": "/tmp/valhalla-bind"},
    )
    result = runner.invoke(app, ["build-routing"])
    assert result.exit_code == 0
    assert "ROCKYROAD_VALHALLA_FILES=/tmp/valhalla-bind" in result.stdout


def test_cli_status_and_help() -> None:
    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    for command in ("update-osm", "build-map", "build-routing", "build-places"):
        assert command in help_result.stdout
    status = runner.invoke(app, ["status"])
    assert status.exit_code == 0


def test_status_requires_artifacts_not_only_manifests(tmp_path: Path, monkeypatch) -> None:
    osm = tmp_path / "osm"
    maps = tmp_path / "maps"
    routing = tmp_path / "routing"
    geo = tmp_path / "geo"
    for directory in (osm, maps, routing, geo):
        directory.mkdir()
        (directory / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("rockyroad_data.cli.OSM_MANIFEST", osm / "manifest.json")
    monkeypatch.setattr("rockyroad_data.cli.MERGED_PBF", osm / "north-america.osm.pbf")
    monkeypatch.setattr("rockyroad_data.cli.MAP_MANIFEST", maps / "manifest.json")
    monkeypatch.setattr("rockyroad_data.cli.PMTILES_PATH", maps / "north-america.pmtiles")
    monkeypatch.setattr("rockyroad_data.cli.ROUTING_MANIFEST", routing / "manifest.json")
    monkeypatch.setattr("rockyroad_data.cli.GEO_MANIFEST", geo / "manifest.json")

    missing = runner.invoke(app, ["status"])
    assert missing.exit_code == 0
    assert missing.stdout.count("missing") == 4

    (osm / "north-america.osm.pbf").write_bytes(b"pbf")
    (maps / "north-america.pmtiles").write_bytes(b"map")
    (routing / "valhalla_tiles.tar").write_bytes(b"tiles")
    for name in ("places", "parks", "campsites", "fuel", "attractions", "boundaries"):
        (geo / f"{name}.parquet").write_bytes(b"parquet")
    ready = runner.invoke(app, ["status"])
    assert ready.exit_code == 0
    assert ready.stdout.count("ready") == 4
