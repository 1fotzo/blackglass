"""Local fork commands. The runner has no broadcast path."""

from __future__ import annotations


class ForkRefusal(Exception):
    """The requested run would leave the local lab."""


def build_anvil_command(
    *,
    fork_block: int | None,
    broadcast: bool,
    rpc_url: str | None,
    port: int = 18545,
) -> list[str]:
    if broadcast:
        raise ForkRefusal("broadcast is refused")
    if fork_block is None:
        raise ForkRefusal("fork mode requires a pinned block")
    if not rpc_url:
        raise ForkRefusal("fork mode requires BLACKGLASS_RPC_URL")
    command = [
        "anvil",
        "--fork-url",
        rpc_url,
        "--fork-block-number",
        str(fork_block),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    if any("broadcast" in part for part in command):
        raise ForkRefusal("broadcast is refused")
    return command
