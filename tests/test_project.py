import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from blackglass.campaign.models import CampaignResult, FindingStatus, Impact, Property, TwinOutcome
from blackglass.cli import app
from blackglass.core.config import ConfigError, load_config
from blackglass.core.importer import import_campaign
from blackglass.core.report import render_report
from blackglass.core.scope import ScopeError, require_address
from blackglass.core.store import open_store

runner = CliRunner()
ADDRESS = "0x" + "ab" * 20


def _result(tmp_path: Path, *, patched_held: bool, status: FindingStatus) -> Path:
    minimized = tmp_path / "Minimized.t.sol"
    minimized.write_text("contract Minimized {}\n", encoding="utf-8")
    payload = CampaignResult(
        id="lab-lending-solvency",
        property=Property(
            id="lab-lending-solvency",
            statement="Pool assets must cover recorded liabilities.",
            impact=Impact.funds,
        ),
        status=status,
        outcome=TwinOutcome(vulnerable_broken=True, patched_held=patched_held),
        minimized_test=str(minimized),
    )
    path = tmp_path / "result.json"
    path.write_text(payload.model_dump_json(), encoding="utf-8")
    return path


def test_config_refuses_secret_keys(tmp_path: Path) -> None:
    path = tmp_path / "blackglass.toml"
    path.write_text('rpc_url = "https://example.invalid/secret"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)
    assert load_config(tmp_path / "missing.toml") == {}


def test_import_requires_scope_and_report_keeps_the_twin_rule(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    project_id = store.create_project("lending", "ada")
    result_path = _result(tmp_path, patched_held=True, status=FindingStatus.reproduced)
    with pytest.raises(ScopeError):
        import_campaign(store, tmp_path, result_path, "lab/lending")

    (tmp_path / "lab" / "lending").mkdir(parents=True)
    store.grant_path(project_id, "lab/lending")
    imported = import_campaign(store, tmp_path, result_path, "lab/lending")
    assert imported.status is FindingStatus.reproduced

    finding = store.findings(project_id)[0]
    evidence = store.evidence_for(int(finding["id"]))
    hashes = {row["sha256"] for row in evidence}
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() in hashes
    assert hashlib.sha256((tmp_path / "Minimized.t.sol").read_bytes()).hexdigest() in hashes

    report = render_report(store, project_id, "lending")
    reproduced, rest = report.split("## Hypotheses", maxsplit=1)
    assert "## Reproduced" in reproduced
    assert "Pool assets must cover recorded liabilities." in reproduced
    assert "Pool assets must cover recorded liabilities." not in rest.split("## Recommendations")[0]

    commands = [row["command"] for row in store.command_log(project_id)]
    assert any(command.startswith("project create") for command in commands)
    assert any(command.startswith("import ") for command in commands)
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute("DELETE FROM command_log")
    store.close()


def test_false_reproduction_stays_a_hypothesis(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    project_id = store.create_project("lending")
    store.grant_path(project_id, "lab/lending")
    result_path = _result(tmp_path, patched_held=False, status=FindingStatus.reproduced)
    imported = import_campaign(store, tmp_path, result_path, "lab/lending")
    assert imported.status is FindingStatus.hypothesis
    report = render_report(store, project_id, "lending")
    reproduced = report.split("## Hypotheses", maxsplit=1)[0]
    assert "Pool assets must cover recorded liabilities." not in reproduced
    store.close()


def test_address_scope_rejects_targets_that_were_not_granted(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    project_id = store.create_project("wallet")
    with pytest.raises(ScopeError):
        require_address(store, project_id, 1, ADDRESS)
    store.grant_address(project_id, 1, ADDRESS.lower())
    assert require_address(store, project_id, 1, ADDRESS) == ADDRESS.lower()
    store.close()


def test_project_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("blackglass.console.repo_root", lambda: tmp_path)
    (tmp_path / "lab" / "lending").mkdir(parents=True)
    created = runner.invoke(app, ["project", "create", "lending", "--owner", "ada"])
    assert created.exit_code == 0
    listed = runner.invoke(app, ["project", "list"])
    assert "lending" in listed.output
    scoped = runner.invoke(app, ["project", "scope", "--path", "lab/lending"])
    assert scoped.exit_code == 0
    result_path = _result(tmp_path, patched_held=True, status=FindingStatus.reproduced)
    imported = runner.invoke(app, ["project", "import", str(result_path), "--path", "lab/lending"])
    assert imported.exit_code == 0
    assert "reproduced" in imported.output
    generated = runner.invoke(app, ["report", "generate"])
    assert generated.exit_code == 0
    report = Path(generated.output.strip()).read_text(encoding="utf-8")
    assert "## Reproduced" in report
    assert "## Hypotheses" in report
    assert "## Recommendations" in report
    duplicate = runner.invoke(app, ["project", "create", "lending"])
    assert duplicate.exit_code == 1
