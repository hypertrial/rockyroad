from __future__ import annotations

from rockyroad_data.paths import REPO_ROOT


def test_dev_script_probes_pmtiles_with_a_byte_range() -> None:
    script = (REPO_ROOT / "scripts" / "dev").read_text(encoding="utf-8")
    assert '-r 0-0 "http://127.0.0.1:8000/maps/north-america.pmtiles"' in script
    assert 'curl -sf -o /dev/null "http://127.0.0.1:8000/maps/north-america.pmtiles"' not in script


def test_caddyfile_does_not_mark_pmtiles_immutable() -> None:
    text = (REPO_ROOT / "Caddyfile").read_text(encoding="utf-8")
    assert "immutable" not in text
    assert "must-revalidate" in text


def test_api_image_includes_regions_config() -> None:
    text = (REPO_ROOT / "infra" / "api" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY config /app/config" in text


def test_compose_sets_osm_dir_on_the_data_volume() -> None:
    text = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "ROCKYROAD_OSM_DIR: /data/osm" in text


def test_map_image_heap_is_overridable() -> None:
    text = (REPO_ROOT / "infra" / "map" / "Dockerfile").read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["java", "-Xmx4g"' not in text
    assert "JAVA_TOOL_OPTIONS" in text


def test_env_example_documents_planetiler_heap() -> None:
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "ROCKYROAD_PLANETILER_XMX" in text
