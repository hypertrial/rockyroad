from __future__ import annotations

from pathlib import Path

import pytest

from rockyroad_data.osm import merge_extracts


def test_merge_extracts_copies_a_single_file(tmp_path: Path) -> None:
    source = tmp_path / "pei.osm.pbf"
    source.write_bytes(b"osm-pbf")
    output = tmp_path / "merged.osm.pbf"
    merge_extracts([source], output)
    assert output.read_bytes() == b"osm-pbf"


def test_merge_extracts_requires_an_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one"):
        merge_extracts([], tmp_path / "merged.osm.pbf")
