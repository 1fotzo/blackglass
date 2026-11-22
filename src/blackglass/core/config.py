"""Load project configuration. Secret material is refused, not stored."""

from __future__ import annotations

import tomllib
from pathlib import Path

FORBIDDEN_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "mnemonic",
        "private_key",
        "privkey",
        "rpc_url",
        "secret",
        "seed",
        "token",
    }
)


class ConfigError(Exception):
    """The configuration file is not safe to load."""


def load_config(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError("configuration must be a table")
    _reject_secrets(data)
    return data


def _reject_secrets(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ConfigError(f"refusing secret key {key}")
            _reject_secrets(item)
        return
    if isinstance(value, list):
        for item in value:
            _reject_secrets(item)
