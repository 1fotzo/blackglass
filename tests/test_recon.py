import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from blackglass.chain.ethereum import ADMIN_SLOT, APPROVAL_TOPIC, IMPL_SLOT, PERMIT2, PERMIT2_TOPIC, UINT160_MAX
from blackglass.chain.etherscan import ENV_KEY, EtherscanClient, client_from_env
from blackglass.chain.keccak import keccak256, selector, topic
from blackglass.chain.service import collect
from blackglass.cli import app
from blackglass.core.report import render_report
from blackglass.core.scope import ScopeError
from blackglass.core.store import open_store

runner = CliRunner()
WALLET = "0x" + "11" * 20
IMPL = "0x" + "22" * 20
ADMIN = "0x" + "33" * 20
ORACLE = "0x" + "44" * 20
SPENDER = "0x" + "55" * 20
TOKEN = "0x" + "66" * 20
PERMIT_TOKEN = "0x" + "77" * 20
DEPLOYER = "0x" + "88" * 20
SECRET = "super-secret-key"


def _word(address: str) -> str:
    return "0x" + address.removeprefix("0x").rjust(64, "0")


def _abi() -> str:
    return json.dumps(
        [
            {
                "type": "function",
                "name": "oracle",
                "stateMutability": "view",
                "inputs": [],
                "outputs": [{"name": "", "type": "address"}],
            }
        ]
    )


class FakeIndexer:
    def __init__(self, symbol: str = "DAI") -> None:
        self.calls: list[tuple[str, str, dict[str, str]]] = []
        self.symbol = symbol

    def fetch(self, chain_id: int, module: str, action: str, params: dict[str, str]) -> object:
        self.calls.append((module, action, dict(params)))
        if action == "eth_getCode":
            return "0x" if params["address"] == SPENDER else "0x60806040"
        if action == "eth_getStorageAt":
            if params["position"] == IMPL_SLOT:
                return _word(IMPL)
            if params["position"] == ADMIN_SLOT:
                return _word(ADMIN)
            return "0x" + "00" * 32
        if action == "getsourcecode":
            if params["address"] == WALLET:
                return [{"ABI": _abi()}]
            return [{"ABI": "Contract source code not verified"}]
        if action == "getcontractcreation":
            return [{"contractCreator": DEPLOYER}]
        if action == "balance":
            return "1000"
        if action == "addresstokenbalance":
            return [{"TokenAddress": TOKEN, "TokenSymbol": self.symbol, "TokenQuantity": "5"}]
        if action == "txlist":
            return [{"from": WALLET, "to": ORACLE, "value": "1", "blockNumber": "90", "hash": "0xabc"}]
        if action == "tokentx":
            return []
        if action == "getLogs" and params.get("topic0") == APPROVAL_TOPIC:
            return [
                {
                    "address": TOKEN,
                    "topics": [APPROVAL_TOPIC, _word(WALLET), _word(SPENDER)],
                    "data": "0x" + "f" * 64,
                    "blockNumber": "91",
                    "logIndex": "1",
                }
            ]
        if action == "getLogs":
            amount = format(UINT160_MAX, "064x")
            return [
                {
                    "address": PERMIT2,
                    "topics": [PERMIT2_TOPIC, _word(WALLET), _word(PERMIT_TOKEN), _word(SPENDER)],
                    "data": "0x" + amount + "00" * 32,
                    "blockNumber": "92",
                    "logIndex": "0",
                }
            ]
        if action == "eth_call":
            return _word(ORACLE)
        raise AssertionError(action)


def _project(tmp_path: Path, *, grant: bool) -> None:
    store = open_store(tmp_path)
    project_id = store.create_project("lending")
    if grant:
        store.grant_address(project_id, 1, WALLET)
    store.close()


def test_keccak_matches_the_erc20_approval_topic() -> None:
    assert keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert topic("Approval(address,address,uint256)") == "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
    assert selector("owner()") == "0x8da5cb5b"


def test_map_records_proxy_exposure_and_does_not_grant_neighbors(tmp_path: Path) -> None:
    _project(tmp_path, grant=True)
    indexer = FakeIndexer()
    summary = collect("map", chain_id=1, address=WALLET, block=100, window=10, indexer=indexer, root=tmp_path)
    assert "kind proxy  verified true" in summary
    assert "unlimited 2" in summary
    assert "discovered 3" in summary
    assert "not a reproduced finding" in summary

    transfer = next(params for module, action, params in indexer.calls if action == "txlist")
    assert transfer["startblock"] == "90"
    assert transfer["endblock"] == "100"

    store = open_store(tmp_path)
    try:
        assert store.in_scope_address(1, 1, ORACLE) is False
        assert store.in_scope_address(1, 1, IMPL) is False
        row = store.recon_rows(1)[0]
        body = json.loads(row["body"])
        assert body["identity"]["deployer"] == DEPLOYER
        assert {item["address"] for item in body["neighbors"]} == {IMPL, ADMIN, ORACLE}
        assert all(item["granted"] is False for item in body["neighbors"])
        commands = [item["command"] for item in store.command_log(1)]
        assert any(command.startswith("recon map ") for command in commands)
        assert not any("scope" in command and ORACLE in command for command in commands)
    finally:
        store.close()


def test_inspect_skips_neighbor_calls(tmp_path: Path) -> None:
    _project(tmp_path, grant=True)
    indexer = FakeIndexer()
    summary = collect("inspect", chain_id=1, address=WALLET, block=100, window=10, indexer=indexer, root=tmp_path)
    assert "discovered 0" in summary
    assert not any(action == "eth_call" for _module, action, _params in indexer.calls)


def test_ungranted_address_is_not_read(tmp_path: Path) -> None:
    _project(tmp_path, grant=False)

    class Boom:
        def fetch(self, chain_id: int, module: str, action: str, params: dict[str, str]) -> object:
            raise AssertionError("indexer was called")

    with pytest.raises(ScopeError):
        collect("map", chain_id=1, address=WALLET, block=100, window=10, indexer=Boom(), root=tmp_path)


def test_window_is_bounded(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="window"):
        collect("map", chain_id=1, address=WALLET, block=100, window=100_001, indexer=FakeIndexer(), root=tmp_path)


def test_report_keeps_observations_out_of_reproduced(tmp_path: Path) -> None:
    _project(tmp_path, grant=True)
    collect("map", chain_id=1, address=WALLET, block=100, window=10, indexer=FakeIndexer(), root=tmp_path)
    store = open_store(tmp_path)
    try:
        report = render_report(store, 1, "lending")
    finally:
        store.close()
    reproduced, rest = report.split("## Hypotheses", maxsplit=1)
    assert "None." in reproduced
    assert ORACLE not in reproduced
    assert "## Observations" in rest
    assert "not reproduced findings" in rest
    assert ORACLE in rest


def test_client_scrubs_the_api_key_and_hides_request_failures() -> None:
    def transport(_url: str) -> dict[str, object]:
        return {"status": "1", "result": f"prefix-{SECRET}"}

    client = EtherscanClient(SECRET, transport)
    assert SECRET not in str(client.fetch(1, "account", "balance", {"address": WALLET}))

    def broken(_url: str) -> dict[str, object]:
        raise TimeoutError(SECRET)

    client = EtherscanClient(SECRET, broken)
    with pytest.raises(Exception, match="indexer request failed") as caught:
        client.fetch(1, "account", "balance", {"address": WALLET})
    assert SECRET not in str(caught.value)


def test_missing_api_key_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_KEY, raising=False)
    monkeypatch.setattr("blackglass.chain.etherscan.load_local_env", lambda: None)
    with pytest.raises(Exception, match=ENV_KEY):
        client_from_env()


def test_env_file_fills_a_missing_key_without_overriding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from blackglass.core.envfile import load_local_env

    env_file = tmp_path / ".env"
    env_file.write_text('BLACKGLASS_ETHERSCAN_API_KEY="from-file"\nBLACKGLASS_RPC_URL=from-file\n', encoding="utf-8")
    monkeypatch.delenv("BLACKGLASS_ETHERSCAN_API_KEY", raising=False)
    monkeypatch.setenv("BLACKGLASS_RPC_URL", "already-set")
    load_local_env(env_file)
    assert os.environ["BLACKGLASS_ETHERSCAN_API_KEY"] == "from-file"
    assert os.environ["BLACKGLASS_RPC_URL"] == "already-set"


def test_cli_map_uses_the_injected_indexer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _project(tmp_path, grant=True)
    indexer = FakeIndexer()
    monkeypatch.setattr("blackglass.chain.service.repo_root", lambda: tmp_path)
    monkeypatch.setattr("blackglass.chain.service.client_from_env", lambda: indexer)
    result = runner.invoke(
        app,
        ["recon", "map", "--chain-id", "1", "--address", WALLET, "--block", "100", "--window", "10"],
    )
    assert result.exit_code == 0
    assert "kind proxy" in result.output
    assert SECRET not in result.output
