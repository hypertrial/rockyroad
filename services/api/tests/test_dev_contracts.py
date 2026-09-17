from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

from rockyroad_data.paths import REPO_ROOT


def test_dev_script_probes_pmtiles_with_a_byte_range() -> None:
    script = (REPO_ROOT / "scripts" / "dev").read_text(encoding="utf-8")
    assert '-r 0-0 "http://127.0.0.1:8000/maps/north-america.pmtiles"' in script
    assert "%{http_code}" in script
    assert 'curl -sf -o /dev/null "http://127.0.0.1:8000/maps/north-america.pmtiles"' not in script
    assert 'curl -sf "http://127.0.0.1:8000/api/ready"' in script


def test_caddyfile_does_not_mark_pmtiles_immutable() -> None:
    text = (REPO_ROOT / "Caddyfile").read_text(encoding="utf-8")
    assert "immutable" not in text
    assert "must-revalidate" in text


def test_api_image_includes_regions_config() -> None:
    text = (REPO_ROOT / "infra" / "api" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY config /app/config" in text


def test_api_image_installs_extensions_for_the_runtime_directory() -> None:
    text = (REPO_ROOT / "infra" / "api" / "Dockerfile").read_text(encoding="utf-8")
    assert 'ROCKYROAD_EXTENSIONS_DIR="/opt/duckdb/extensions"' in text
    assert "SET extension_directory='/opt/duckdb/extensions'" in text
    assert "chown -R rockyroad:rockyroad /opt/duckdb /state" in text
    assert 'ENTRYPOINT ["rockyroad-api-entrypoint"]' in text


def test_api_entrypoint_migrates_legacy_compose_database_once(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy" / "rockyroad.duckdb"
    target = tmp_path / "state" / "rockyroad.duckdb"
    legacy.parent.mkdir()
    legacy.write_bytes(b"legacy database")
    legacy.with_suffix(".duckdb.wal").write_bytes(b"legacy wal")
    entrypoint = REPO_ROOT / "infra" / "api" / "entrypoint.sh"
    env = {
        **os.environ,
        "ROCKYROAD_LEGACY_DUCKDB_PATH": str(legacy),
        "ROCKYROAD_DUCKDB_PATH": str(target),
    }

    first = subprocess.run(
        ["sh", str(entrypoint), "sh", "-c", "printf command-ran"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert target.read_bytes() == b"legacy database"
    assert target.with_suffix(".duckdb.wal").read_bytes() == b"legacy wal"
    assert "Migrated the legacy RockyRoad database" in first.stdout
    assert first.stdout.endswith("command-ran")

    target.write_bytes(b"current database")
    second = subprocess.run(["sh", str(entrypoint), "true"], env=env, text=True, capture_output=True, check=True)
    assert target.read_bytes() == b"current database"
    assert "Migrated" not in second.stdout


def test_compose_sets_osm_dir_on_the_data_volume() -> None:
    config = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    api = config["services"]["api"]
    assert api["environment"]["ROCKYROAD_OSM_DIR"] == "/data/osm"
    assert api["environment"]["ROCKYROAD_DUCKDB_PATH"] == "/state/rockyroad.duckdb"
    assert "rockyroad-state:/state" in api["volumes"]
    assert "./data:/data:ro" in api["volumes"]
    assert "rockyroad-state" in config["volumes"]


def test_map_image_heap_is_overridable() -> None:
    text = (REPO_ROOT / "infra" / "map" / "Dockerfile").read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["java", "-Xmx4g"' not in text
    assert "JAVA_TOOL_OPTIONS" in text


def test_env_example_documents_planetiler_heap() -> None:
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "ROCKYROAD_PLANETILER_XMX" in text
    assert "ROCKYROAD_PROVIDER_MODE=hosted" in text
    assert "ROCKYROAD_ORS_API_KEY" in text


def test_compose_keeps_valhalla_on_local_profile() -> None:
    text = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "ROCKYROAD_PROVIDER_MODE" in text
    assert 'profiles: ["local"]' in text
    assert "ROCKYROAD_ORS_API_KEY" in text
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "docker compose --profile local config" in ci


def test_dev_script_checks_hosted_ors_key() -> None:
    script = (REPO_ROOT / "scripts" / "dev").read_text(encoding="utf-8")
    assert "ROCKYROAD_ORS_API_KEY" in script
    assert "--profile local up -d valhalla" in script
    assert 'PYTHONPATH="$root/services/api/src' in script
    assert "OpenFreeMap Liberty" in script


def test_dev_script_prefers_exported_provider_settings() -> None:
    script = (REPO_ROOT / "scripts" / "dev").read_text(encoding="utf-8")
    assert "${ROCKYROAD_PROVIDER_MODE+x}" in script
    assert "${ROCKYROAD_ORS_API_KEY+x}" in script


def test_dev_script_honors_an_explicitly_empty_ors_key(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "dev"
    script.write_text((REPO_ROOT / "scripts" / "dev").read_text(encoding="utf-8"), encoding="utf-8")
    script.chmod(0o755)
    for directory in (root / ".venv", root / "node_modules", root / "apps" / "web" / "node_modules"):
        directory.mkdir(parents=True)
    (root / ".env").write_text(
        "ROCKYROAD_PROVIDER_MODE=hosted\nROCKYROAD_ORS_API_KEY=from-env-file\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "curl").write_text(
        '#!/bin/sh\ncase "$*" in *api/ready*) exit 1;; *api/health*) exit 0;; esac\nexit 0\n',
        encoding="utf-8",
    )
    for name in ("curl", "uv", "pnpm"):
        path = bin_dir / name
        if name != "curl":
            path.write_text("#!/bin/sh\nsleep 1\n", encoding="utf-8")
        path.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "ROCKYROAD_ORS_API_KEY": ""}

    result = subprocess.run([str(script)], cwd=root, env=env, text=True, capture_output=True, timeout=10, check=True)

    assert "Hosted routing needs ROCKYROAD_ORS_API_KEY" in result.stdout


def test_compose_forwards_photon_user_agent() -> None:
    config = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    value = config["services"]["api"]["environment"]["ROCKYROAD_PHOTON_USER_AGENT"]
    assert value.startswith("${ROCKYROAD_PHOTON_USER_AGENT:-RockyRoad/")
