from __future__ import annotations

from pathlib import Path

import pytest

from rockyroad_data.maps import build_map, require_planetiler


def test_require_planetiler_does_not_download(tmp_path: Path) -> None:
    missing = tmp_path / "planetiler.jar"
    with pytest.raises(FileNotFoundError, match="offline"):
        require_planetiler(missing)
    assert not missing.exists()


def test_require_planetiler_rejects_tiny_jar(tmp_path: Path) -> None:
    tiny = tmp_path / "planetiler.jar"
    tiny.write_bytes(b"too-small")
    with pytest.raises(FileNotFoundError, match="offline"):
        require_planetiler(tiny)


def test_build_map_does_not_pass_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    jar = tmp_path / "planetiler.jar"
    jar.write_bytes(b"0" * 1_000_001)
    pbf = tmp_path / "north-america.osm.pbf"
    pbf.write_bytes(b"pbf")
    maps_dir = tmp_path / "maps"
    captured: dict[str, list[str]] = {}

    def fake_run(args: list[str], **_kwargs: object) -> None:
        captured["args"] = list(args)
        output = Path(args[args.index("--output") + 1])
        output.write_bytes(b"pmtiles")

    monkeypatch.setattr("rockyroad_data.maps.require_java", lambda: "java")
    monkeypatch.setattr("rockyroad_data.maps.run_command", fake_run)
    monkeypatch.setattr("rockyroad_data.maps.ensure_data_dirs", lambda: None)

    manifest = build_map(pbf=pbf, output_dir=maps_dir, jar=jar)
    assert "--download" not in captured["args"]
    assert str(jar) in captured["args"]
    assert (maps_dir / "north-america.pmtiles").exists()
    assert manifest["pmtiles"]["exists"] is True
