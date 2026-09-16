from __future__ import annotations

from pathlib import Path

import pytest

from rockyroad_data.maps import build_map, planetiler_xmx, require_planetiler
from rockyroad_data.paths import REPO_ROOT
from rockyroad_data.process import ToolError


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
    captured: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> None:
        captured["args"] = list(args)
        captured["cwd"] = kwargs.get("cwd")
        output = Path(args[args.index("--output") + 1])
        output.write_bytes(b"pmtiles")

    monkeypatch.delenv("ROCKYROAD_PLANETILER_XMX", raising=False)
    monkeypatch.setattr("rockyroad_data.maps.require_java", lambda: "java")
    monkeypatch.setattr("rockyroad_data.maps.run_command", fake_run)
    monkeypatch.setattr("rockyroad_data.maps.ensure_data_dirs", lambda: None)

    manifest = build_map(pbf=pbf, output_dir=maps_dir, jar=jar)
    args = captured["args"]
    assert isinstance(args, list)
    assert "--download" not in args
    assert str(jar) in args
    assert "-Xmx4g" in args
    assert captured["cwd"] == REPO_ROOT
    assert (maps_dir / "north-america.pmtiles").exists()
    assert manifest["pmtiles"]["exists"] is True


def test_build_map_heap_follows_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    jar = tmp_path / "planetiler.jar"
    jar.write_bytes(b"0" * 1_000_001)
    pbf = tmp_path / "north-america.osm.pbf"
    pbf.write_bytes(b"pbf")
    captured: dict[str, list[str]] = {}

    def fake_run(args: list[str], **_kwargs: object) -> None:
        captured["args"] = list(args)
        Path(args[args.index("--output") + 1]).write_bytes(b"pmtiles")

    monkeypatch.setenv("ROCKYROAD_PLANETILER_XMX", "32g")
    monkeypatch.setattr("rockyroad_data.maps.require_java", lambda: "java")
    monkeypatch.setattr("rockyroad_data.maps.run_command", fake_run)
    monkeypatch.setattr("rockyroad_data.maps.ensure_data_dirs", lambda: None)

    build_map(pbf=pbf, output_dir=tmp_path / "maps", jar=jar)
    assert "-Xmx32g" in captured["args"]
    assert "-Xmx4g" not in captured["args"]


def test_planetiler_xmx_rejects_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROCKYROAD_PLANETILER_XMX", "-Xmx32g; rm -rf /")
    with pytest.raises(ToolError, match="4g or 32g"):
        planetiler_xmx()
