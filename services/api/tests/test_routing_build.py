from __future__ import annotations

from pathlib import Path

import pytest

from rockyroad_data.process import ToolError, docker_can_bind
from rockyroad_data.routing import VALHALLA_IMAGE, _publish_directories, build_routing, docker_files_dir


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


def test_nested_docker_override_does_not_modify_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "north-america.osm.pbf"
    source.write_bytes(b"pbf")
    dest = tmp_path / "valhalla"
    dest.mkdir()
    (dest / "valhalla.json").write_text('{"mjolnir": {}}', encoding="utf-8")
    (dest / "valhalla_tiles.tar").write_bytes(b"old tiles")
    (dest / "manifest.json").write_text("old manifest", encoding="utf-8")
    nested = dest / "cache"
    monkeypatch.setenv("ROCKYROAD_VALHALLA_FILES", str(nested))
    monkeypatch.setattr("rockyroad_data.routing.shutil.which", lambda _name: None)
    monkeypatch.setattr("rockyroad_data.routing.require_executable", lambda _name: "docker")
    monkeypatch.setattr("rockyroad_data.routing.ensure_data_dirs", lambda: None)

    with pytest.raises(ToolError, match="must not be nested"):
        build_routing(pbf=source, output_dir=dest)

    assert not nested.exists()
    assert (dest / "valhalla.json").read_text(encoding="utf-8") == '{"mjolnir": {}}'
    assert (dest / "valhalla_tiles.tar").read_bytes() == b"old tiles"
    assert (dest / "manifest.json").read_text(encoding="utf-8") == "old manifest"


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
        (host / "valhalla.json").write_text(
            '{"mjolnir": {"tile_extract": "/custom_files/valhalla_tiles.tar"}}\n', encoding="utf-8"
        )

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
    home = tmp_path / "home"
    home.mkdir()
    dest = home / "valhalla"
    commands: list[list[str]] = []

    def fake_which(name: str) -> str | None:
        if name in {"valhalla_build_tiles", "valhalla_build_extract"}:
            return f"/usr/bin/{name}"
        return None

    def fake_run(args: list[str], **_kwargs: object) -> None:
        commands.append(list(args))
        config = Path(args[args.index("-c") + 1])
        (config.parent / "valhalla_tiles.tar").write_bytes(b"tiles")

    monkeypatch.delenv("ROCKYROAD_VALHALLA_FILES", raising=False)
    monkeypatch.setattr("rockyroad_data.process.Path.home", lambda: home)
    monkeypatch.setattr("rockyroad_data.routing.shutil.which", fake_which)
    monkeypatch.setattr("rockyroad_data.routing.run_command", fake_run)
    monkeypatch.setattr("rockyroad_data.routing.ensure_data_dirs", lambda: None)

    manifest = build_routing(pbf=source, output_dir=dest)
    assert commands[0][0] == "/usr/bin/valhalla_build_tiles"
    assert commands[1][0] == "/usr/bin/valhalla_build_extract"
    assert all(args[0] != "docker" for args in commands)
    assert str(dest / "valhalla_tiles") in (dest / "valhalla.json").read_text(encoding="utf-8")
    assert Path(manifest["docker_files"]) == dest.resolve()


def test_build_routing_host_tools_stage_spaced_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "north-america.osm.pbf"
    source.write_bytes(b"pbf")
    dest = tmp_path / "Mac SSD" / "valhalla"
    dest.mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    commands: list[list[str]] = []

    def fake_which(name: str) -> str | None:
        if name in {"valhalla_build_tiles", "valhalla_build_extract"}:
            return f"/usr/bin/{name}"
        return None

    def fake_run(args: list[str], **_kwargs: object) -> None:
        commands.append(list(args))
        config = Path(args[args.index("-c") + 1])
        (config.parent / "valhalla_tiles.tar").write_bytes(b"tiles")

    monkeypatch.delenv("ROCKYROAD_VALHALLA_FILES", raising=False)
    monkeypatch.setattr("rockyroad_data.routing.Path.home", lambda: home)
    monkeypatch.setattr("rockyroad_data.routing.shutil.which", fake_which)
    monkeypatch.setattr("rockyroad_data.routing.run_command", fake_run)
    monkeypatch.setattr("rockyroad_data.routing.ensure_data_dirs", lambda: None)

    manifest = build_routing(pbf=source, output_dir=dest)
    cache = (home / ".cache" / "rockyroad" / "valhalla").resolve()
    assert all(args[0] != "docker" for args in commands)
    assert Path(manifest["docker_files"]) == cache
    assert (cache / "valhalla_tiles.tar").is_file()
    assert (dest / "valhalla_tiles.tar").is_file()


def test_build_routing_host_tools_honor_valhalla_files_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "north-america.osm.pbf"
    source.write_bytes(b"pbf")
    home = tmp_path / "home"
    home.mkdir()
    dest = home / "valhalla"
    override = tmp_path / "bindable-override"
    commands: list[list[str]] = []

    def fake_which(name: str) -> str | None:
        if name in {"valhalla_build_tiles", "valhalla_build_extract"}:
            return f"/usr/bin/{name}"
        return None

    def fake_run(args: list[str], **_kwargs: object) -> None:
        commands.append(list(args))
        config = Path(args[args.index("-c") + 1])
        (config.parent / "valhalla_tiles.tar").write_bytes(b"tiles")

    monkeypatch.setenv("ROCKYROAD_VALHALLA_FILES", str(override))
    monkeypatch.setattr("rockyroad_data.process.Path.home", lambda: home)
    monkeypatch.setattr("rockyroad_data.routing.shutil.which", fake_which)
    monkeypatch.setattr("rockyroad_data.routing.run_command", fake_run)
    monkeypatch.setattr("rockyroad_data.routing.ensure_data_dirs", lambda: None)

    manifest = build_routing(pbf=source, output_dir=dest)
    cache = (home / ".cache" / "rockyroad" / "valhalla").resolve()
    assert all(args[0] != "docker" for args in commands)
    assert Path(manifest["docker_files"]) == override.resolve()
    assert Path(manifest["docker_files"]) != dest.resolve()
    assert Path(manifest["docker_files"]) != cache
    assert (override / "valhalla_tiles.tar").is_file()
    assert (dest / "valhalla_tiles.tar").is_file()
    assert not cache.exists()


def test_failed_host_rebuild_preserves_live_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "north-america.osm.pbf"
    source.write_bytes(b"pbf")
    home = tmp_path / "home"
    dest = home / "valhalla"
    dest.mkdir(parents=True)
    (dest / "valhalla.json").write_text("old config", encoding="utf-8")
    (dest / "valhalla_tiles.tar").write_bytes(b"old tiles")
    (dest / "manifest.json").write_text("old manifest", encoding="utf-8")

    monkeypatch.delenv("ROCKYROAD_VALHALLA_FILES", raising=False)
    monkeypatch.setattr("rockyroad_data.process.Path.home", lambda: home)
    monkeypatch.setattr(
        "rockyroad_data.routing._host_valhalla_tools",
        lambda: ("valhalla_build_tiles", "valhalla_build_extract"),
    )
    monkeypatch.setattr("rockyroad_data.routing.ensure_data_dirs", lambda: None)

    def fail_after_writing(args: list[str], **_kwargs: object) -> None:
        config = Path(args[args.index("-c") + 1])
        (config.parent / "valhalla_tiles.tar").write_bytes(b"partial new tiles")
        raise ToolError("build failed")

    monkeypatch.setattr("rockyroad_data.routing.run_command", fail_after_writing)

    with pytest.raises(ToolError, match="build failed"):
        build_routing(pbf=source, output_dir=dest)

    assert (dest / "valhalla.json").read_text(encoding="utf-8") == "old config"
    assert (dest / "valhalla_tiles.tar").read_bytes() == b"old tiles"
    assert (dest / "manifest.json").read_text(encoding="utf-8") == "old manifest"


def test_build_refuses_to_replace_a_directory_with_unmanaged_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "north-america.osm.pbf"
    source.write_bytes(b"pbf")
    home = tmp_path / "home"
    dest = home / "shared"
    dest.mkdir(parents=True)
    sentinel = dest / "keep-me.txt"
    sentinel.write_text("unrelated", encoding="utf-8")
    monkeypatch.delenv("ROCKYROAD_VALHALLA_FILES", raising=False)
    monkeypatch.setattr("rockyroad_data.process.Path.home", lambda: home)
    monkeypatch.setattr(
        "rockyroad_data.routing._host_valhalla_tools",
        lambda: ("valhalla_build_tiles", "valhalla_build_extract"),
    )
    monkeypatch.setattr("rockyroad_data.routing.ensure_data_dirs", lambda: None)

    with pytest.raises(ToolError, match="unmanaged entries"):
        build_routing(pbf=source, output_dir=dest)

    assert sentinel.read_text(encoding="utf-8") == "unrelated"


def test_build_preserves_unmanaged_file_created_during_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "north-america.osm.pbf"
    source.write_bytes(b"pbf")
    home = tmp_path / "home"
    dest = home / "valhalla"
    dest.mkdir(parents=True)
    (dest / "valhalla.json").write_text('{"mjolnir": {}}', encoding="utf-8")
    (dest / "valhalla_tiles.tar").write_bytes(b"old tiles")
    (dest / "manifest.json").write_text("old manifest", encoding="utf-8")
    monkeypatch.delenv("ROCKYROAD_VALHALLA_FILES", raising=False)
    monkeypatch.setattr("rockyroad_data.process.Path.home", lambda: home)
    monkeypatch.setattr(
        "rockyroad_data.routing._host_valhalla_tools",
        lambda: ("valhalla_build_tiles", "valhalla_build_extract"),
    )
    monkeypatch.setattr("rockyroad_data.routing.ensure_data_dirs", lambda: None)

    def finish_build_after_unmanaged_file_arrives(args: list[str], **_kwargs: object) -> None:
        config = Path(args[args.index("-c") + 1])
        (config.parent / "valhalla_tiles.tar").write_bytes(b"new tiles")
        (dest / "arrived-during-build.txt").write_text("keep me", encoding="utf-8")

    monkeypatch.setattr("rockyroad_data.routing.run_command", finish_build_after_unmanaged_file_arrives)

    with pytest.raises(ToolError, match="unmanaged entries"):
        build_routing(pbf=source, output_dir=dest)

    assert (dest / "arrived-during-build.txt").read_text(encoding="utf-8") == "keep me"
    assert (dest / "valhalla_tiles.tar").read_bytes() == b"old tiles"
    assert (dest / "manifest.json").read_text(encoding="utf-8") == "old manifest"


def test_failed_docker_rebuild_preserves_runtime_and_mirror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "north-america.osm.pbf"
    source.write_bytes(b"pbf")
    dest = tmp_path / "Mac SSD" / "valhalla"
    runtime = tmp_path / "docker-cache" / "valhalla"
    for directory in (dest, runtime):
        directory.mkdir(parents=True)
        (directory / "valhalla.json").write_text("old config", encoding="utf-8")
        (directory / "valhalla_tiles.tar").write_bytes(b"old tiles")
    (dest / "manifest.json").write_text("old manifest", encoding="utf-8")
    monkeypatch.setenv("ROCKYROAD_VALHALLA_FILES", str(runtime))
    monkeypatch.setattr("rockyroad_data.routing.shutil.which", lambda _name: None)
    monkeypatch.setattr("rockyroad_data.routing.require_executable", lambda _name: "docker")
    monkeypatch.setattr("rockyroad_data.routing.ensure_data_dirs", lambda: None)

    def fail_after_writing(args: list[str], **_kwargs: object) -> None:
        mount = Path(args[args.index("-v") + 1].split(":", 1)[0])
        (mount / "valhalla_tiles.tar").write_bytes(b"partial new tiles")
        (mount / "valhalla.json").write_text("new config", encoding="utf-8")
        raise ToolError("docker build failed")

    monkeypatch.setattr("rockyroad_data.routing.run_command", fail_after_writing)

    with pytest.raises(ToolError, match="docker build failed"):
        build_routing(pbf=source, output_dir=dest)

    for directory in (dest, runtime):
        assert (directory / "valhalla.json").read_text(encoding="utf-8") == "old config"
        assert (directory / "valhalla_tiles.tar").read_bytes() == b"old tiles"
    assert (dest / "manifest.json").read_text(encoding="utf-8") == "old manifest"


def test_invalid_docker_output_preserves_runtime_and_mirror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "north-america.osm.pbf"
    source.write_bytes(b"pbf")
    dest = tmp_path / "Mac SSD" / "valhalla"
    runtime = tmp_path / "docker-cache" / "valhalla"
    for directory in (dest, runtime):
        directory.mkdir(parents=True)
        (directory / "valhalla.json").write_text('{"mjolnir": {}}', encoding="utf-8")
        (directory / "valhalla_tiles.tar").write_bytes(b"old tiles")
    (dest / "manifest.json").write_text("old manifest", encoding="utf-8")
    monkeypatch.setenv("ROCKYROAD_VALHALLA_FILES", str(runtime))
    monkeypatch.setattr("rockyroad_data.routing.shutil.which", lambda _name: None)
    monkeypatch.setattr("rockyroad_data.routing.require_executable", lambda _name: "docker")
    monkeypatch.setattr("rockyroad_data.routing.ensure_data_dirs", lambda: None)

    def write_invalid_output(args: list[str], **_kwargs: object) -> None:
        mount = Path(args[args.index("-v") + 1].split(":", 1)[0])
        (mount / "valhalla_tiles.tar").write_bytes(b"new tiles")
        (mount / "valhalla.json").write_text("not json", encoding="utf-8")

    monkeypatch.setattr("rockyroad_data.routing.run_command", write_invalid_output)

    with pytest.raises(ToolError, match="did not produce"):
        build_routing(pbf=source, output_dir=dest)

    for directory in (dest, runtime):
        assert (directory / "valhalla.json").read_text(encoding="utf-8") == '{"mjolnir": {}}'
        assert (directory / "valhalla_tiles.tar").read_bytes() == b"old tiles"
    assert (dest / "manifest.json").read_text(encoding="utf-8") == "old manifest"


def test_directory_publish_rolls_back_an_earlier_swap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    staged_first = tmp_path / "staged-first"
    staged_second = tmp_path / "staged-second"
    for path, value in (
        (first, "old first"),
        (second, "old second"),
        (staged_first, "new first"),
        (staged_second, "new second"),
    ):
        path.mkdir()
        (path / "manifest.json").write_text(value, encoding="utf-8")

    replace = Path.replace

    def fail_second(source: Path, target: Path) -> Path:
        if source == staged_second:
            raise OSError("publish failed")
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_second)

    with pytest.raises(OSError, match="publish failed"):
        _publish_directories([(staged_first, first), (staged_second, second)])

    assert (first / "manifest.json").read_text(encoding="utf-8") == "old first"
    assert (second / "manifest.json").read_text(encoding="utf-8") == "old second"


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
