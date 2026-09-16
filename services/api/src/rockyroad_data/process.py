from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


class ToolError(RuntimeError):
    pass


def docker_can_bind(path: Path) -> bool:
    resolved = path.resolve()
    if " " in str(resolved):
        return False
    try:
        resolved.relative_to(Path.home().resolve())
        return True
    except ValueError:
        return sys.platform.startswith("linux")


def docker_stage_dir(dest: Path, *, env_var: str, cache_name: str) -> Path:
    override = os.environ.get(env_var)
    if override:
        path = Path(override).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()
    resolved = dest.resolve()
    if docker_can_bind(resolved):
        return resolved
    path = Path.home() / ".cache" / "rockyroad" / cache_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def require_executable(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise ToolError(f"required executable is not on PATH: {name}")
    return path


def _java_major(java_bin: str) -> int | None:
    completed = subprocess.run([java_bin, "-version"], check=False, capture_output=True, text=True)
    text = f"{completed.stderr}\n{completed.stdout}"
    match = re.search(r'version "(\d+)', text)
    return int(match.group(1)) if match else None


def require_java(min_major: int = 21) -> str:
    candidates: list[str] = []
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append(str(Path(java_home) / "bin" / "java"))
    for helper in ("/usr/libexec/java_home",):
        if Path(helper).exists():
            probed = subprocess.run([helper, "-v", f"{min_major}+"], check=False, capture_output=True, text=True)
            if probed.returncode == 0 and probed.stdout.strip():
                candidates.append(str(Path(probed.stdout.strip()) / "bin" / "java"))
    for extra in (
        Path("/opt/homebrew/opt/openjdk@21/bin/java"),
        Path("/opt/homebrew/opt/openjdk@25/bin/java"),
        Path("/opt/homebrew/opt/openjdk/bin/java"),
    ):
        if extra.exists():
            candidates.append(str(extra))
    which = shutil.which("java")
    if which:
        candidates.append(which)

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen or not Path(candidate).exists():
            continue
        seen.add(candidate)
        major = _java_major(candidate)
        if major is not None and major >= min_major:
            return candidate
    raise ToolError(
        f"Java {min_major}+ is required for Planetiler. Install Temurin/OpenJDK {min_major} or set JAVA_HOME."
    )


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
