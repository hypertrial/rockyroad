from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from rockyroad_data.paths import REPO_ROOT


def test_dev_script_probes_pmtiles_with_a_byte_range() -> None:
    script = (REPO_ROOT / "scripts" / "dev").read_text(encoding="utf-8")
    assert '-r 0-0 "$api_origin/maps/north-america.pmtiles"' in script
    assert "%{http_code}" in script
    assert 'curl -sf -o /dev/null "http://127.0.0.1:8000/maps/north-america.pmtiles"' not in script
    assert '--max-time 1 "$api_origin/api/ready"' in script
    assert '--max-time 1 "$api_origin/api/health"' in script


def test_secret_env_files_are_excluded_from_docker_build_context() -> None:
    rules = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in rules
    assert ".env.*" in rules
    assert "!.env.example" in rules
    assert rules.index("!.env.example") > rules.index(".env.*")


def test_offline_smoke_uses_the_local_compose_profile() -> None:
    script = (REPO_ROOT / "scripts" / "offline-smoke.sh").read_text(encoding="utf-8")
    assert "docker-compose --profile local config" in script
    assert "docker compose --profile local config" in script
    assert "ROCKYROAD_PROVIDER_MODE=local docker compose --profile local up --build" in script


def test_offline_docs_set_local_mode_on_assembled_compose() -> None:
    docs = (REPO_ROOT / "docs" / "data-build.md").read_text(encoding="utf-8")
    script = (REPO_ROOT / "scripts" / "offline-smoke.sh").read_text(encoding="utf-8")
    assembled = "ROCKYROAD_PROVIDER_MODE=local docker compose --profile local up --build"
    assert assembled in docs
    assert assembled in script
    compose = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "ROCKYROAD_PROVIDER_MODE: ${ROCKYROAD_PROVIDER_MODE:-hosted}" in compose


def test_make_fmt_only_invokes_installed_formatter() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    fmt_recipe = makefile.split("fmt:\n", 1)[1].split("\nlint:", 1)[0]
    assert "ruff format" in fmt_recipe
    assert "prettier" not in fmt_recipe
    assert "|| true" not in fmt_recipe


def test_ci_targets_github_hosted_ubuntu() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert all(job["runs-on"] == "ubuntu-latest" for job in jobs.values())

    triggers = workflow.get("on", workflow.get(True))
    assert triggers == {"push": {"branches": ["main"]}, "workflow_dispatch": None}
    assert workflow["permissions"] == {"contents": "read"}

    steps = [step for job in jobs.values() for step in job["steps"]]
    commands = [step["run"] for step in steps if "run" in step]
    actions = [step["uses"] for step in steps if "uses" in step]
    assert "./scripts/verify" in commands
    assert "pnpm --filter @rockyroad/web exec playwright install --with-deps chromium" in commands
    assert all("self-hosted" not in str(job.get("runs-on")) for job in jobs.values())
    revisions = [action.rsplit("@", 1)[1] for action in actions]
    assert all(len(revision) == 40 and set(revision) <= set("0123456789abcdef") for revision in revisions)
    checkout = next(step for step in steps if step.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["persist-credentials"] is False


def test_vite_proxies_to_the_server_only_dev_api_origin() -> None:
    config = (REPO_ROOT / "apps" / "web" / "vite.config.ts").read_text(encoding="utf-8")
    assert "ROCKYROAD_DEV_API_ORIGIN" in config
    assert '"/api": apiOrigin' in config
    assert '"/maps": apiOrigin' in config
    assert "VITE_ROCKYROAD_DEV_API_ORIGIN" not in config


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
    assert "127.0.0.1:8080:80" in text
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "./scripts/verify" in ci
    verify = (REPO_ROOT / "scripts" / "verify").read_text(encoding="utf-8")
    assert "make compose-config" in verify
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "--profile local config" in makefile


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


def test_dev_script_waits_past_the_old_startup_deadline(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "dev"
    script.write_text((REPO_ROOT / "scripts" / "dev").read_text(encoding="utf-8"), encoding="utf-8")
    script.chmod(0o755)
    for directory in (root / ".venv", root / "node_modules", root / "apps" / "web" / "node_modules"):
        directory.mkdir(parents=True)
    (root / ".env").write_text("ROCKYROAD_PROVIDER_MODE=hosted\n", encoding="utf-8")

    count_file = tmp_path / "health-probes"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "curl").write_text(
        """#!/bin/sh
case "$*" in
  *api/ready*) exit 1 ;;
  *api/health*)
    count=0
    if [ -f "$ROCKYROAD_TEST_CURL_COUNT" ]; then count="$(cat "$ROCKYROAD_TEST_CURL_COUNT")"; fi
    count=$((count + 1))
    printf '%s\n' "$count" > "$ROCKYROAD_TEST_CURL_COUNT"
    [ "$count" -ge 82 ]
    exit
    ;;
esac
exit 0
""",
        encoding="utf-8",
    )
    (bin_dir / "uv").write_text(
        """#!/bin/sh
while :; do
  count=0
  if [ -f "$ROCKYROAD_TEST_CURL_COUNT" ]; then count="$(cat "$ROCKYROAD_TEST_CURL_COUNT")"; fi
  [ "${count:-0}" -ge 82 ] && exit 0
  /bin/sleep 0.05
done
""",
        encoding="utf-8",
    )
    (bin_dir / "pnpm").write_text("#!/bin/sh\n/bin/sleep 0.1\n", encoding="utf-8")
    (bin_dir / "sleep").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for path in bin_dir.iterdir():
        path.chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROCKYROAD_DEV_API_TIMEOUT_SECONDS": "21",
        "ROCKYROAD_TEST_CURL_COUNT": str(count_file),
    }
    result = subprocess.run([str(script)], cwd=root, env=env, text=True, capture_output=True, timeout=30, check=True)

    assert int(count_file.read_text(encoding="utf-8")) == 82
    assert "RockyRoad is running." in result.stdout


@pytest.mark.parametrize(
    ("configured_host", "expected_origin"),
    [
        ("0.0.0.0", "http://127.0.0.1:9123"),
        ("::", "http://[::1]:9123"),
        ("::1", "http://[::1]:9123"),
    ],
)
def test_dev_script_uses_configured_api_origin_for_health_and_vite(
    tmp_path: Path, configured_host: str, expected_origin: str
) -> None:
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "dev"
    script.write_text((REPO_ROOT / "scripts" / "dev").read_text(encoding="utf-8"), encoding="utf-8")
    script.chmod(0o755)
    for directory in (root / ".venv", root / "node_modules", root / "apps" / "web" / "node_modules"):
        directory.mkdir(parents=True)
    (root / ".env").write_text(
        f"ROCKYROAD_API_HOST={configured_host}\nROCKYROAD_API_PORT=9123\nROCKYROAD_PROVIDER_MODE=hosted\n",
        encoding="utf-8",
    )

    curl_log = tmp_path / "curl.log"
    vite_origin = tmp_path / "vite-origin"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "curl").write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$ROCKYROAD_TEST_CURL_LOG"
case "$*" in *api/ready*) exit 1;; *api/health*) exit 0;; esac
exit 0
""",
        encoding="utf-8",
    )
    (bin_dir / "uv").write_text("#!/bin/sh\n/bin/sleep 0.2\n", encoding="utf-8")
    (bin_dir / "pnpm").write_text(
        '#!/bin/sh\nprintf \'%s\' "$ROCKYROAD_DEV_API_ORIGIN" > "$ROCKYROAD_TEST_VITE_ORIGIN"\n',
        encoding="utf-8",
    )
    for path in bin_dir.iterdir():
        path.chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROCKYROAD_TEST_CURL_LOG": str(curl_log),
        "ROCKYROAD_TEST_VITE_ORIGIN": str(vite_origin),
    }
    result = subprocess.run([str(script)], cwd=root, env=env, text=True, capture_output=True, timeout=10, check=True)

    assert f"Starting RockyRoad API on {expected_origin}" in result.stdout
    assert f"{expected_origin}/api/ready" in curl_log.read_text(encoding="utf-8")
    assert f"{expected_origin}/api/health" in curl_log.read_text(encoding="utf-8")
    assert vite_origin.read_text(encoding="utf-8") == expected_origin


def test_compose_forwards_photon_user_agent() -> None:
    config = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    value = config["services"]["api"]["environment"]["ROCKYROAD_PHOTON_USER_AGENT"]
    assert value.startswith("${ROCKYROAD_PHOTON_USER_AGENT:-RockyRoad/")
