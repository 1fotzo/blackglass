"""Scope is checked before a command touches a target."""

from __future__ import annotations

import re
from pathlib import Path

from blackglass.core.store import Store

_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


class ScopeError(Exception):
    """The target is not granted on this project."""


def normalize_address(address: str) -> str:
    if not _ADDRESS.fullmatch(address):
        raise ScopeError("address must be a 0x-prefixed 20-byte hex value")
    return address.lower()


def normalize_path(root: Path, raw: str) -> str:
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    root_resolved = root.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ScopeError("path is outside the repository")
    return resolved.relative_to(root_resolved).as_posix()


def require_path(store: Store, project_id: int, root: Path, raw: str) -> str:
    relative = normalize_path(root, raw)
    if not store.in_scope_path(project_id, relative):
        raise ScopeError(f"{relative} is not in scope")
    return relative


def require_address(store: Store, project_id: int, chain_id: int, address: str) -> str:
    normalized = normalize_address(address)
    if not store.in_scope_address(project_id, chain_id, normalized):
        raise ScopeError(f"{normalized} on chain {chain_id} is not in scope")
    return normalized
