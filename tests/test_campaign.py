import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from blackglass.campaign.forge_parse import parse_sequence, suite_failed
from blackglass.campaign.fork import ForkRefusal, build_anvil_command
from blackglass.campaign.minimize import render_minimized_test, shrink
from blackglass.campaign.models import (
    CallStep,
    CampaignResult,
    CorpusCase,
    FindingStatus,
    Impact,
    Property,
    TwinOutcome,
    judge,
)
from blackglass.campaign.runner import repo_root, run_lab
from blackglass.campaign.score import collect_rows, render_score
from blackglass.cli import app

runner = CliRunner()

VULNERABLE_OUTPUT = """
[FAIL: assertion failed] test_solvency_sequence() (gas: 10)
[Sequence]
sender=0x1 addr=[test/Vulnerable.t.sol:VulnerableInvariant] calldata=deposit(uint96) args=[1000000000000000000 [1e18]]
sender=0x1 addr=[test/Vulnerable.t.sol:VulnerableInvariant] calldata=noise(uint96) args=[1]
sender=0x1 addr=[test/Vulnerable.t.sol:VulnerableInvariant] calldata=withdraw(uint96) args=[1000000000000000000 [1e18]]
sender=0x1 addr=[test/Vulnerable.t.sol:VulnerableInvariant] calldata=deposit(uint96) args=[2]
[FAIL: assertion failed] invariant_solvency() (runs: 2, calls: 8, reverts: 0)
"""

PATCHED_OUTPUT = """
[PASS] test_solvency_sequence() (gas: 10)
[PASS] invariant_solvency() (runs: 2, calls: 8, reverts: 0)
"""


def test_reproduced_requires_both_twins() -> None:
    assert judge(TwinOutcome(vulnerable_broken=True, patched_held=True)) is FindingStatus.reproduced
    assert judge(TwinOutcome(vulnerable_broken=False, patched_held=True)) is FindingStatus.rejected
    assert judge(TwinOutcome(vulnerable_broken=True, patched_held=False)) is FindingStatus.hypothesis
    assert judge(TwinOutcome(vulnerable_broken=None, patched_held=True)) is FindingStatus.hypothesis


def test_forge_parser_reads_failures_and_calls() -> None:
    assert suite_failed(VULNERABLE_OUTPUT, 1) is True
    assert suite_failed(PATCHED_OUTPUT, 0) is False
    assert suite_failed("Compiler run failed", 1) is None
    steps = parse_sequence(VULNERABLE_OUTPUT)
    assert [step.name for step in steps] == ["deposit", "noise", "withdraw", "deposit"]
    assert steps[0].arg == 10**18


def test_shrink_drops_calls_that_are_not_required() -> None:
    steps = parse_sequence(VULNERABLE_OUTPUT)

    def breaks(trial: list[CallStep]) -> bool:
        names = [step.name for step in trial]
        return "deposit" in names and "withdraw" in names and names.index("deposit") < names.index("withdraw")

    shrunk = shrink(steps, breaks)
    assert [step.name for step in shrunk] == ["deposit", "withdraw"]


def test_minimized_test_replays_the_sequence() -> None:
    source = render_minimized_test([CallStep(name="deposit", arg=10**18), CallStep(name="withdraw", arg=10**18)])
    assert "pool.withdraw(1000000000000000000);" in source
    assert "pool.liabilities()" in source


def test_fork_command_stays_local_and_refuses_broadcast() -> None:
    command = build_anvil_command(fork_block=100, broadcast=False, rpc_url="https://example.invalid")
    assert command[0] == "anvil"
    assert "127.0.0.1" in command
    assert "--fork-block-number" in command
    assert all("broadcast" not in part for part in command)
    with pytest.raises(ForkRefusal):
        build_anvil_command(fork_block=100, broadcast=True, rpc_url="https://example.invalid")
    with pytest.raises(ForkRefusal):
        build_anvil_command(fork_block=None, broadcast=False, rpc_url="https://example.invalid")


def test_corpus_has_ten_honest_lending_cases() -> None:
    cases = list((repo_root() / "corpus" / "cases").glob("*.json"))
    assert len(cases) >= 10
    for path in cases:
        case = CorpusCase.model_validate(json.loads(path.read_text(encoding="utf-8")))
        assert case.outcome == "inconclusive"
        assert case.source_url.startswith("https://")
        assert "exploit" not in case.property.lower()


def test_corpus_file_cannot_mark_itself_reproduced() -> None:
    with pytest.raises(ValueError):
        CorpusCase.model_validate(
            {
                "id": "x",
                "title": "X",
                "domain": "lending",
                "chain_id": 1,
                "property": "Assets cover liabilities.",
                "impact": "funds",
                "source_url": "https://example.invalid",
                "outcome": "reproduced",
            }
        )


def test_score_fails_when_a_patched_twin_breaks(tmp_path: Path) -> None:
    corpus = repo_root() / "corpus" / "cases"
    campaign = tmp_path / "lab-lending-solvency"
    campaign.mkdir()
    result = CampaignResult(
        id="lab-lending-solvency",
        property=Property(id="lab-lending-solvency", statement="Assets cover liabilities.", impact=Impact.funds),
        status=FindingStatus.hypothesis,
        outcome=TwinOutcome(vulnerable_broken=True, patched_held=False),
    )
    (campaign / "result.json").write_text(result.model_dump_json(), encoding="utf-8")
    rows, code = collect_rows(corpus, tmp_path)
    assert code == 1
    assert "broken" in render_score(rows)


def test_lab_run_marks_the_harness_reproduced(tmp_path: Path) -> None:
    def forge_run(lab: Path, match: str) -> subprocess.CompletedProcess[str]:
        if match == "Vulnerable":
            return subprocess.CompletedProcess(args=[], returncode=1, stdout=VULNERABLE_OUTPUT, stderr="")
        if match == "Patched":
            return subprocess.CompletedProcess(args=[], returncode=0, stdout=PATCHED_OUTPUT, stderr="")
        source = (lab / "test" / "Minimized.t.sol").read_text(encoding="utf-8")
        deposit_at = source.find("pool.deposit")
        withdraw_at = source.find("pool.withdraw")
        breaks = deposit_at != -1 and withdraw_at != -1 and deposit_at < withdraw_at
        stdout = "[FAIL: assertion failed] test_minimized()" if breaks else "[PASS] test_minimized()"
        return subprocess.CompletedProcess(args=[], returncode=1 if breaks else 0, stdout=stdout, stderr="")

    result = run_lab(campaign_dir=tmp_path, forge_run=forge_run)
    assert result.status is FindingStatus.reproduced
    assert result.outcome.patched_held is True
    assert result.minimized_test is not None
    assert [step.name for step in result.sequence] == ["deposit", "withdraw"]
    saved = Path(result.minimized_test).read_text(encoding="utf-8")
    assert "pool.withdraw" in saved


def test_harness_pair_differs_by_the_liability_update() -> None:
    root = repo_root() / "lab" / "lending" / "src"
    vulnerable = (root / "VulnerablePool.sol").read_text(encoding="utf-8")
    patched = (root / "PatchedPool.sol").read_text(encoding="utf-8")
    assert "PATCH:" not in vulnerable
    assert "liabilities -=" not in vulnerable
    assert "PATCH:" in patched


def test_broadcast_is_refused() -> None:
    result = runner.invoke(app, ["campaign", "run", "--broadcast"])
    assert result.exit_code == 1
    assert "broadcast" in (result.output + (result.stderr or "")).lower()


def test_corpus_score_command_lists_inconclusive_cases() -> None:
    result = runner.invoke(app, ["corpus", "score"])
    assert result.exit_code == 0
    assert "euler-2023-03" in result.output
    assert "inconclusive" in result.output
