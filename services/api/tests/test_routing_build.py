from __future__ import annotations

from pathlib import Path

import pytest

from rockyroad_data.process import ToolError, docker_can_bind
from rockyroad_data.routing import VALHALLA_IMAGE, build_routing, docker_files_dir


def test_docker_can_bind_rejects_spaces() -> None:
    assert docker_can_bind(Path("/Volumes/Mac SSD/data")) is False


def test_docker_files_dir_stages_spaced_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    dest = tmp_path / "Mac SSD" / "valhalla"
    dest.mkdir(parents=True)
    monkeypatch.delenv("ROCKYROAD_VALHALLA_FILES", raising=False)
    monkeypatch.setattr("rockyroad_data.process.Path.home", lambda: home)
    assert docker_files_dir(dest) == (home / ".cache" / "rockyroad" / "valhalla").resolve()


def test_docker_files_dir_uses_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    override = tmp_path / "bind"
    monkeypatch.setenv("ROCKYROAD_VALHALLA_FILES", str(override))
    assert docker_files_dir(tmp_path / "valhalla") == override.resolve()


def test_build_routing_uses_docker_when_host_tools_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "north-america.osm.pbf"
    source.write_bytes(b"pbf")
    dest = tmp_path / "valhalla"
    bind = tmp_path / "bind"
    captured: dict[str, list[str]] = {}
    monkeypatch.setenv("ROCKYROAD_VALHALLA_FILES", str(bind))

    def fake_run(args: list[str], **_kwargs: object) -> None:
        captured["args"] = list(args)
        mount = args[args.index("-v") + 1]
        host = Path(mount.split(":", 1)[0])
        (host / "valhalla_tiles.tar").write_bytes(b"tiles")
        (host / "valhalla.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr("rockyroad_data.routing.shutil.which", lambda _name: None)
    monkeypatch.setattr("rockyroad_data.routing.require_executable", lambda _name: "docker")
    monkeypatch.setattr("rockyroad_data.routing.run_command", fake_run)
    monkeypatch.setattr("rockyroad_data.routing.ensure_data_dirs", lambda: None)

    manifest = build_routing(pbf=source, output_dir=dest)
    mount = captured["args"][captured["args"].index("-v") + 1]
    assert captured["args"][0] == "docker"
    assert VALHALLA_IMAGE in captured["args"]
    assert "serve_tiles=False" in captured["args"]
    assert "force_rebuild=True" in captured["args"]
    assert "use_default_speeds_config=False" in captured["args"]
    assert "tile_urls=" in captured["args"]
    assert captured["args"].count("-v") == 1
    assert " " not in mount.split(":", 1)[0]
    assert source.exists()
    assert not (dest / source.name).exists()
    assert manifest["tiles"]["exists"] is True
    assert (dest / "manifest.json").exists()
    assert (dest / "valhalla_tiles.tar").exists()


def test_build_routing_prefers_host_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "north-america.osm.pbf"
    source.write_bytes(b"pbf")
    dest = tmp_path / "valhalla"
    commands: list[list[str]] = []

    def fake_which(name: str) -> str | None:
        if name in {"valhalla_build_tiles", "valhalla_build_extract"}:
            return f"/usr/bin/{name}"
        return None

    def fake_run(args: list[str], **_kwargs: object) -> None:
        commands.append(list(args))
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "valhalla_tiles.tar").write_bytes(b"tiles")

    monkeypatch.setattr("rockyroad_data.routing.shutil.which", fake_which)
    monkeypatch.setattr("rockyroad_data.routing.run_command", fake_run)
    monkeypatch.setattr("rockyroad_data.routing.ensure_data_dirs", lambda: None)

    build_routing(pbf=source, output_dir=dest)
    assert commands[0][0] == "/usr/bin/valhalla_build_tiles"
    assert commands[1][0] == "/usr/bin/valhalla_build_extract"
    assert all(args[0] != "docker" for args in commands)


def test_build_routing_requires_docker_or_host_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "north-america.osm.pbf"
    source.write_bytes(b"pbf")
    monkeypatch.setattr("rockyroad_data.routing.shutil.which", lambda _name: None)
    monkeypatch.setattr(
        "rockyroad_data.routing.require_executable",
        lambda _name: (_ for _ in ()).throw(ToolError("missing")),
    )
    monkeypatch.setattr("rockyroad_data.routing.ensure_data_dirs", lambda: None)
    with pytest.raises(ToolError, match="Docker"):
        build_routing(pbf=source, output_dir=tmp_path / "valhalla")
