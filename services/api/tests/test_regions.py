from __future__ import annotations

from pathlib import Path

import pytest

from rockyroad_data.regions import RegionConfigError, geofabrik_urls, load_regions, profile_bounds, resolve_profile


def test_sample_profile_is_allow_listed() -> None:
    config = load_regions()
    name, extracts = resolve_profile(config, "sample")
    assert name == "sample"
    assert extracts == ["north-america/canada/prince-edward-island"]
    assert profile_bounds(config, "sample") == [-64.45, 45.90, -61.90, 47.10]
    assert profile_bounds(config, "missing") is None
    url, md5 = geofabrik_urls(config, extracts[0])
    assert url.endswith("prince-edward-island-latest.osm.pbf")
    assert md5.endswith(".md5")


def test_unknown_extract_is_rejected() -> None:
    config = load_regions()
    with pytest.raises(RegionConfigError):
        geofabrik_urls(config, "europe/germany")


def test_full_profile_contains_canada_and_us() -> None:
    config = load_regions()
    _, extracts = resolve_profile(config, "canada-usa")
    assert extracts == ["north-america/canada", "north-america/us"]


def test_invalid_yaml_rejected(tmp_path: Path) -> None:
    path = tmp_path / "regions.yaml"
    path.write_text("- just a list\n", encoding="utf-8")
    with pytest.raises(RegionConfigError):
        load_regions(path)
