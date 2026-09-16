from __future__ import annotations

from typer.testing import CliRunner

from rockyroad_data.cli import app

runner = CliRunner()


def test_cli_status_and_help() -> None:
    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    for command in ("update-osm", "build-map", "build-routing", "build-places"):
        assert command in help_result.stdout
    status = runner.invoke(app, ["status"])
    assert status.exit_code == 0
