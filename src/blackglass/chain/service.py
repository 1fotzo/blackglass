"""Store a pinned recon map or wallet exposure on the open project."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import typer

from blackglass.campaign.runner import repo_root
from blackglass.chain.ethereum import Indexer, ReconError, read_map
from blackglass.chain.etherscan import client_from_env
from blackglass.chain.models import ReconMap
from blackglass.core.config import ConfigError, load_config
from blackglass.core.scope import ScopeError, require_address
from blackglass.core.store import open_store

MAX_WINDOW = 100_000
DEFAULT_WINDOW = 5_000


class RecordingIndexer:
    def __init__(self, inner: Indexer) -> None:
        self._inner = inner
        self.sources: list[tuple[str, str]] = []

    def fetch(self, chain_id: int, module: str, action: str, params: dict[str, str]) -> object:
        result = self._inner.fetch(chain_id, module, action, params)
        payload = json.dumps(result, sort_keys=True, separators=(",", ":"), default=str)
        self.sources.append((f"etherscan:{module}.{action}", payload))
        return result


def collect(
    kind: str,
    *,
    chain_id: int,
    address: str,
    block: int,
    window: int = DEFAULT_WINDOW,
    indexer: Indexer | None = None,
    root: Path | None = None,
) -> str:
    """Read one scoped address and store the observation. Neighbors are not granted."""
    if chain_id <= 0:
        raise ReconError("chain id must be positive")
    if block < 0:
        raise ReconError("block must be zero or greater")
    if window < 1 or window > MAX_WINDOW:
        raise ReconError(f"window must be from 1 to {MAX_WINDOW} blocks")
    repo = repo_root() if root is None else root
    load_config(repo / "blackglass.toml")
    store = open_store(repo)
    try:
        project = store.current()
        if project is None:
            raise ReconError("no project is open")
        project_id = int(project["id"])
        granted = require_address(store, project_id, chain_id, address)
        reader = RecordingIndexer(indexer or client_from_env())
        recon = read_map(
            reader,
            chain_id,
            granted,
            block,
            max(0, block - window),
            include_neighbors=kind == "map",
        )
        for neighbor in recon.neighbors:
            neighbor.granted = store.in_scope_address(project_id, chain_id, neighbor.address)
        body = json.dumps(recon.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        recon_id = store.add_recon(
            project_id,
            chain_id=chain_id,
            address=granted,
            block=block,
            kind=kind,
            body=body,
            sha256=digest,
        )
        for source, payload in reader.sources:
            store.add_recon_source(
                recon_id,
                source=source,
                sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            )
        store.log(project_id, f"recon {kind} chain={chain_id} address={granted} block={block}")
    finally:
        store.close()
    return summarize(recon)


def summarize(recon: ReconMap) -> str:
    unlimited = sum(1 for item in recon.approvals if item.unlimited)
    discovered = [item.address for item in recon.neighbors if not item.granted]
    lines = [
        f"{recon.identity.address}  chain {recon.identity.chain_id}  block {recon.identity.block}",
        f"kind {recon.identity.kind.value}  verified {str(recon.identity.verified).lower()}",
        f"native {recon.native_balance_wei}  tokens {len(recon.tokens)}",
        f"transfers {len(recon.transfers)}  approvals {len(recon.approvals)}  unlimited {unlimited}",
        f"discovered {len(discovered)}",
        "observation  not a reproduced finding",
    ]
    return "\n".join(lines)


def do_recon_map(
    chain_id: int,
    address: str,
    block: int,
    window: int = DEFAULT_WINDOW,
    indexer: Indexer | None = None,
) -> None:
    """Map one scoped address at a pinned block."""
    _run("map", chain_id, address, block, window, indexer)


def do_wallet_inspect(
    chain_id: int,
    address: str,
    block: int,
    window: int = DEFAULT_WINDOW,
    indexer: Indexer | None = None,
) -> None:
    """Read balances, transfers, and approvals for one scoped address."""
    _run("inspect", chain_id, address, block, window, indexer)


def _run(kind: str, chain_id: int, address: str, block: int, window: int, indexer: Indexer | None) -> None:
    try:
        typer.echo(collect(kind, chain_id=chain_id, address=address, block=block, window=window, indexer=indexer))
    except (ReconError, ScopeError, ConfigError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
