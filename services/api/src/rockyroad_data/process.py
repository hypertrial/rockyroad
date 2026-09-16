from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path


class ToolError(RuntimeError):
    pass


def require_executable(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise ToolError(f"required executable is not on PATH: {name}")
    return path


def run_command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(args),
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise ToolError(f"command failed ({completed.returncode}): {' '.join(args)}\n{detail}")
    return completed
