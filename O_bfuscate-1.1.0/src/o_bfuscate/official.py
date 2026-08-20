from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def bundled_compiler() -> Path:
    candidates = (
        Path(__file__).resolve().parents[1] / "vendor" / "luau" / "linux-x86_64" / "luau-compile",
        Path(sys.prefix) / "share" / "o_bfuscate" / "vendor" / "luau" / "linux-x86_64" / "luau-compile",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def find_compiler(explicit: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    env = os.environ.get("O_BFUSCATE_LUAU_COMPILER")
    if env:
        candidates.append(Path(env))
    candidates.append(bundled_compiler())
    on_path = shutil.which("luau-compile")
    if on_path:
        candidates.append(Path(on_path))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def validate_source(source: str, compiler: Path) -> tuple[bool, str]:
    """Compile source with the official Luau compiler without retaining bytecode."""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".luau", delete=False) as handle:
        handle.write(source)
        path = Path(handle.name)
    try:
        completed = subprocess.run(
            [str(compiler), "--binary", "-O1", "-g0", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return completed.returncode == 0, completed.stderr.strip()
    finally:
        path.unlink(missing_ok=True)


def bundled_runtime() -> Path:
    candidates = (
        Path(__file__).resolve().parents[1] / "vendor" / "luau" / "linux-x86_64" / "luau",
        Path(sys.prefix) / "share" / "o_bfuscate" / "vendor" / "luau" / "linux-x86_64" / "luau",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def find_runtime(explicit: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    env = os.environ.get("O_BFUSCATE_LUAU_RUNTIME")
    if env:
        candidates.append(Path(env))
    candidates.append(bundled_runtime())
    on_path = shutil.which("luau")
    if on_path:
        candidates.append(Path(on_path))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def execute_source(source: str, runtime: Path, *, timeout: float = 10.0) -> tuple[int, str, str]:
    """Execute source with the official Luau CLI in an isolated temporary file."""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".luau", delete=False) as handle:
        handle.write(source)
        path = Path(handle.name)
    try:
        completed = subprocess.run(
            [str(runtime), str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout,
        )
        return completed.returncode, completed.stdout, completed.stderr
    finally:
        path.unlink(missing_ok=True)
