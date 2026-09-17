from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from rockyroad_api.geo import extract_bounds
from rockyroad_data.osm import merge_extracts, update_osm


def test_merge_extracts_copies_a_single_file(tmp_path: Path) -> None:
    source = tmp_path / "pei.osm.pbf"
    source.write_bytes(b"osm-pbf")
    output = tmp_path / "merged.osm.pbf"
    merge_extracts([source], output)
    assert output.read_bytes() == b"osm-pbf"


def test_merge_extracts_requires_an_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one"):
        merge_extracts([], tmp_path / "merged.osm.pbf")


def test_update_osm_persists_custom_profile_bounds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    osm_dir = tmp_path / "osm"
    osm_dir.mkdir()
    manifest_path = osm_dir / "manifest.json"
    merged_path = osm_dir / "north-america.osm.pbf"
    regions = tmp_path / "regions.yaml"
    regions.write_text(
        """geofabrik_base: https://example.test
default_profile: sample
profiles:
  sample:
    bounds: [-120, 48, -110, 60]
    extracts: [north-america/canada/alberta]
""",
        encoding="utf-8",
    )

    def fake_download(_url: str, destination: Path, **_kwargs):
        if destination.suffix == ".md5":
            destination.write_text(
                f"{hashlib.md5(b'pbf', usedforsecurity=False).hexdigest()}  source\n", encoding="utf-8"
            )
        else:
            destination.write_bytes(b"pbf")
        return {"changed": True, "etag": "v1", "path": str(destination)}

    monkeypatch.setattr("rockyroad_data.osm.OSM_DIR", osm_dir)
    monkeypatch.setattr("rockyroad_data.osm.OSM_MANIFEST", manifest_path)
    monkeypatch.setattr("rockyroad_data.osm.MERGED_PBF", merged_path)
    monkeypatch.setattr("rockyroad_data.osm.ensure_data_dirs", lambda: None)
    monkeypatch.setattr("rockyroad_data.osm.download_file", fake_download)

    manifest = update_osm("sample", regions)

    assert manifest["bounds"] == [-120.0, 48.0, -110.0, 60.0]
    assert extract_bounds(osm_dir) == [-120.0, 48.0, -110.0, 60.0]
