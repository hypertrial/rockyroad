from __future__ import annotations

from pathlib import Path

from rockyroad_data.paths import find_repo_root


def test_repo_root_contains_config() -> None:
    root = find_repo_root()
    assert (root / "config" / "regions.yaml").exists()
    assert root == Path.cwd() or "rockyroad" in root.name.lower()
