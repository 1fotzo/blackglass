"""Load a local .env file. Values already in the environment stay as they are."""

from __future__ import annotations

import os
from pathlib import Path


def load_local_env(*paths: Path) -> None:
    """Fill empty environment variables from .env files. Never overwrite."""
    candidates = list(paths) if paths else _default_paths()
    for path in candidates:
        if not path.is_file():
            continue
        for key, value in _parse(path):
            if key and value and key not in os.environ:
                os.environ[key] = value


def _default_paths() -> list[Path]:
    paths = [Path.cwd() / ".env"]
    start = Path(__file__).resolve()
    for parent in start.parents:
        if (parent / "pyproject.toml").is_file():
            repo_env = parent / ".env"
            if repo_env not in paths:
                paths.append(repo_env)
            break
    return paths


def _parse(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        rows.append((key.strip(), _unquote(value.strip())))
    return rows


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value
