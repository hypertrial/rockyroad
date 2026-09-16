from __future__ import annotations

from pathlib import Path

import pytest

from rockyroad_data.process import ToolError, _java_major, require_java


def test_java_major_parses_openjdk_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "rockyroad_data.process.subprocess.run",
        lambda *_args, **_kwargs: type("Result", (), {"stderr": 'openjdk version "21.0.12.1"', "stdout": ""})(),
    )
    assert _java_major("/opt/java/bin/java") == 21


def test_require_java_errors_when_no_runtime_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setattr("rockyroad_data.process.shutil.which", lambda _name: None)
    monkeypatch.setattr(Path, "exists", lambda _self: False)
    with pytest.raises(ToolError, match="Java 21"):
        require_java()
