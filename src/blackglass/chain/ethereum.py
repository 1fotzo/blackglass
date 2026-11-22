"""Classify one address and read its exposure from an indexer."""

from __future__ import annotations

import json
from typing import Protocol

from blackglass.chain.keccak import selector, topic
from blackglass.chain.models import (
    AddressKind,
    Approval,
    Identity,
    Neighbor,
    ReconMap,
    SpenderKind,
    TokenBalance,
    Transfer,
)

IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
PERMIT2 = "0x000000000022d473030f116ddee9f6b43ac78ba3"
APPROVAL_TOPIC = topic("Approval(address,address,uint256)")
PERMIT2_TOPIC = topic("Approval(address,address,address,uint160,uint48)")
UINT256_MAX = (1 << 256) - 1
UINT160_MAX = (1 << 160) - 1
MAX_TRANSFERS = 200
MAX_NEIGHBOR_CALLS = 32
ZERO = "0x" + "0" * 40


class Indexer(Protocol):
    def fetch(self, chain_id: int, module: str, action: str, params: dict[str, str]) -> object:
        """Return the indexer result payload."""


class ReconError(Exception):
    """A pinned read could not be completed."""


def read_map(
    indexer: Indexer,
    chain_id: int,
    address: str,
    block: int,
    window_start: int,
    *,
    include_neighbors: bool,
) -> ReconMap:
    identity = _identity(indexer, chain_id, address, block)
    native = _text(indexer.fetch(chain_id, "account", "balance", {"address": address, "tag": str(block)}))
    tokens = _tokens(indexer, chain_id, address)
    transfers, truncated = _transfers(indexer, chain_id, address, window_start, block)
    approvals = _approvals(indexer, chain_id, address, window_start, block)
    neighbors = _neighbors(indexer, chain_id, address, block, identity) if include_neighbors else []
    return ReconMap(
        identity=identity,
        native_balance_wei=native,
        tokens=tokens,
        transfers=transfers,
        transfers_truncated=truncated,
        approvals=approvals,
        neighbors=neighbors,
        window_start=window_start,
        block=block,
    )


def _identity(indexer: Indexer, chain_id: int, address: str, block: int) -> Identity:
    code = _text(indexer.fetch(chain_id, "proxy", "eth_getCode", {"address": address, "tag": hex(block)}))
    implementation = _slot(indexer, chain_id, address, block, IMPL_SLOT)
    admin = _slot(indexer, chain_id, address, block, ADMIN_SLOT)
    verified, _abi = _source(indexer, chain_id, address)
    has_code = code not in {"0x", "0x0"} and len(code) > 2
    if implementation is not None:
        kind = AddressKind.proxy
    elif has_code:
        kind = AddressKind.contract
    else:
        kind = AddressKind.eoa
    deployer = None
    if has_code or implementation is not None:
        deployer = _deployer(indexer, chain_id, address)
    return Identity(
        chain_id=chain_id,
        address=address,
        block=block,
        kind=kind,
        implementation=implementation,
        admin=admin,
        verified=verified,
        deployer=deployer,
    )


def _tokens(indexer: Indexer, chain_id: int, address: str) -> list[TokenBalance]:
    rows = _as_list(
        indexer.fetch(chain_id, "account", "addresstokenbalance", {"address": address, "page": "1", "offset": "100"})
    )
    balances: list[TokenBalance] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        token = _address(str(row.get("TokenAddress", "")))
        if token is None:
            continue
        balances.append(
            TokenBalance(
                token=token,
                symbol=str(row.get("TokenSymbol", "")),
                amount=str(row.get("TokenQuantity", "0")),
            )
        )
    return balances


def _transfers(
    indexer: Indexer,
    chain_id: int,
    address: str,
    start: int,
    block: int,
) -> tuple[list[Transfer], bool]:
    bounds = {"address": address, "startblock": str(start), "endblock": str(block), "page": "1", "offset": "1000"}
    native = _as_list(indexer.fetch(chain_id, "account", "txlist", bounds))
    tokens = _as_list(indexer.fetch(chain_id, "account", "tokentx", bounds))
    found: list[Transfer] = []
    found.extend(_transfer_rows(native, address, token_key=None))
    found.extend(_transfer_rows(tokens, address, token_key="contractAddress"))
    found.sort(key=lambda item: item.block)
    truncated = len(found) > MAX_TRANSFERS
    if truncated:
        found = found[-MAX_TRANSFERS:]
    return found, truncated


def _transfer_rows(rows: list[object], address: str, *, token_key: str | None) -> list[Transfer]:
    transfers: list[Transfer] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sender = _address(str(row.get("from", "")))
        receiver = _address(str(row.get("to", "")))
        if sender == address:
            direction = "out"
            counterparty = receiver or ZERO
        elif receiver == address:
            direction = "in"
            counterparty = sender or ZERO
        else:
            continue
        token = _address(str(row.get(token_key, ""))) if token_key else None
        transfers.append(
            Transfer(
                block=_as_int(row.get("blockNumber", 0)),
                tx=str(row.get("hash", "")),
                token=token,
                direction=direction,
                counterparty=counterparty,
                amount=str(row.get("value", "0")),
            )
        )
    return transfers


def _approvals(indexer: Indexer, chain_id: int, address: str, start: int, block: int) -> list[Approval]:
    owner = _pad(address)
    erc20 = _as_list(
        indexer.fetch(
            chain_id,
            "logs",
            "getLogs",
            {
                "fromBlock": str(start),
                "toBlock": str(block),
                "topic0": APPROVAL_TOPIC,
                "topic1": owner,
                "topic0_1_opr": "and",
            },
        )
    )
    permit2 = _as_list(
        indexer.fetch(
            chain_id,
            "logs",
            "getLogs",
            {
                "address": PERMIT2,
                "fromBlock": str(start),
                "toBlock": str(block),
                "topic0": PERMIT2_TOPIC,
                "topic1": owner,
                "topic0_1_opr": "and",
            },
        )
    )
    latest: dict[tuple[str, str, str], tuple[int, int, Approval]] = {}
    for log in erc20:
        parsed = _erc20_approval(log)
        if parsed is not None:
            _keep_latest(latest, log, parsed)
    for log in permit2:
        parsed = _permit2_approval(log)
        if parsed is not None:
            _keep_latest(latest, log, parsed)
    approvals = [item for _key, item in sorted(((key, value[2]) for key, value in latest.items()), key=lambda pair: pair[0])]
    for approval in approvals:
        approval.spender_kind = _spender_kind(indexer, chain_id, block, approval.spender)
    return approvals


def _neighbors(
    indexer: Indexer,
    chain_id: int,
    address: str,
    block: int,
    identity: Identity,
) -> list[Neighbor]:
    found: list[Neighbor] = []
    seen: set[str] = set()

    def add(candidate: str | None, relation: str, source: str) -> None:
        if candidate is None or candidate == ZERO or candidate == address or candidate in seen:
            return
        seen.add(candidate)
        found.append(Neighbor(address=candidate, relation=relation, source=source, granted=False))

    add(identity.implementation, "implementation", "eip-1967")
    add(identity.admin, "admin", "eip-1967")
    _verified, abi = _source(indexer, chain_id, address)
    calls = 0
    for item in abi:
        if calls >= MAX_NEIGHBOR_CALLS or not _address_view(item):
            continue
        calls += 1
        signature = f"{item['name']}({','.join(arg['type'] for arg in item.get('inputs', []))})"
        result = indexer.fetch(
            chain_id,
            "proxy",
            "eth_call",
            {"to": address, "data": selector(signature), "tag": hex(block)},
        )
        add(_address_from_word(_text(result)), "referenced", signature)
    return found


def _spender_kind(indexer: Indexer, chain_id: int, block: int, spender: str) -> SpenderKind:
    code = _text(indexer.fetch(chain_id, "proxy", "eth_getCode", {"address": spender, "tag": hex(block)}))
    if code in {"0x", "0x0"} or len(code) <= 2:
        return SpenderKind.eoa
    verified, _abi = _source(indexer, chain_id, spender)
    return SpenderKind.verified if verified else SpenderKind.unverified


def _slot(indexer: Indexer, chain_id: int, address: str, block: int, slot: str) -> str | None:
    word = indexer.fetch(
        chain_id,
        "proxy",
        "eth_getStorageAt",
        {"address": address, "position": slot, "tag": hex(block)},
    )
    return _address_from_word(_text(word))


def _source(indexer: Indexer, chain_id: int, address: str) -> tuple[bool, list[dict[str, object]]]:
    result = indexer.fetch(chain_id, "contract", "getsourcecode", {"address": address})
    rows = result if isinstance(result, list) else []
    item = rows[0] if rows and isinstance(rows[0], dict) else {}
    abi_text = str(item.get("ABI", ""))
    if not abi_text.startswith("["):
        return False, []
    try:
        abi = json.loads(abi_text)
    except json.JSONDecodeError:
        return False, []
    if not isinstance(abi, list):
        return False, []
    return True, [entry for entry in abi if isinstance(entry, dict)]


def _deployer(indexer: Indexer, chain_id: int, address: str) -> str | None:
    result = indexer.fetch(chain_id, "contract", "getcontractcreation", {"contractaddresses": address})
    rows = result if isinstance(result, list) else []
    if not rows or not isinstance(rows[0], dict):
        return None
    return _address(str(rows[0].get("contractCreator", "")))


def _erc20_approval(log: object) -> Approval | None:
    if not isinstance(log, dict):
        return None
    topics = log.get("topics") or []
    if len(topics) < 3 or str(topics[0]).lower() != APPROVAL_TOPIC:
        return None
    token = _address(str(log.get("address", "")))
    spender = _address_from_word(str(topics[2]))
    if token is None or spender is None:
        return None
    amount = _word(str(log.get("data", "0x")), 0)
    return Approval(
        standard="erc20",
        token=token,
        spender=spender,
        amount=str(amount),
        unlimited=amount >= UINT256_MAX,
        spender_kind=SpenderKind.unknown,
    )


def _permit2_approval(log: object) -> Approval | None:
    if not isinstance(log, dict):
        return None
    topics = log.get("topics") or []
    if len(topics) < 4 or str(topics[0]).lower() != PERMIT2_TOPIC:
        return None
    token = _address_from_word(str(topics[2]))
    spender = _address_from_word(str(topics[3]))
    if token is None or spender is None:
        return None
    amount = _word(str(log.get("data", "0x")), 0)
    return Approval(
        standard="permit2",
        token=token,
        spender=spender,
        amount=str(amount),
        unlimited=amount >= UINT160_MAX,
        spender_kind=SpenderKind.unknown,
    )


def _keep_latest(
    latest: dict[tuple[str, str, str], tuple[int, int, Approval]],
    log: object,
    approval: Approval,
) -> None:
    if not isinstance(log, dict):
        return
    key = (approval.standard, approval.token, approval.spender)
    block = _as_int(log.get("blockNumber", 0))
    index = _as_int(log.get("logIndex", 0))
    current = latest.get(key)
    if current is None or (block, index) >= (current[0], current[1]):
        latest[key] = (block, index, approval)


def _address_view(item: dict[str, object]) -> bool:
    if item.get("type") != "function":
        return False
    if item.get("stateMutability") not in {"view", "pure"}:
        return False
    inputs = item.get("inputs")
    outputs = item.get("outputs")
    if not isinstance(inputs, list) or inputs:
        return False
    if not isinstance(outputs, list) or len(outputs) != 1 or not isinstance(outputs[0], dict):
        return False
    return outputs[0].get("type") == "address" and isinstance(item.get("name"), str)


def _as_list(result: object) -> list[object]:
    if result is None or result == "" or result == "0":
        return []
    if isinstance(result, list):
        return result
    raise ReconError("indexer returned an unexpected list payload")


def _text(result: object) -> str:
    if isinstance(result, str):
        return result
    raise ReconError("indexer returned an unexpected value")


def _address(value: str) -> str | None:
    text = value.lower()
    if not text.startswith("0x"):
        return None
    body = text.removeprefix("0x")
    if len(body) != 40 or any(char not in "0123456789abcdef" for char in body):
        return None
    return "0x" + body


def _address_from_word(word: str) -> str | None:
    body = word.lower().removeprefix("0x")
    if len(body) < 40 or any(char not in "0123456789abcdef" for char in body):
        return None
    if int(body, 16) == 0:
        return None
    return "0x" + body[-40:]


def _pad(address: str) -> str:
    return "0x" + address.removeprefix("0x").rjust(64, "0")


def _word(data: str, index: int) -> int:
    body = data.lower().removeprefix("0x")
    chunk = body[index * 64 : (index + 1) * 64]
    if len(chunk) < 64:
        return 0
    return int(chunk, 16)


def _as_int(value: object) -> int:
    if isinstance(value, int):
        return value
    text = str(value)
    return int(text, 16) if text.startswith(("0x", "0X")) else int(text or "0")
