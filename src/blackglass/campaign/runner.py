"""Run the local lending twins. Forge decides whether a finding is reproduced."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from blackglass.campaign.forge_parse import parse_sequence, suite_failed
from blackglass.campaign.fork import ForkRefusal, build_anvil_command
from blackglass.campaign.minimize import render_minimized_test, shrink
from blackglass.campaign.models import (
    CallStep,
    CampaignResult,
    FindingStatus,
    Impact,
    Property,
    TwinOutcome,
    judge,
)

LAB_ID = "lab-lending-solvency"
ForgeRun = Callable[[Path, str], subprocess.CompletedProcess[str]]


class ForgeNotFound(Exception):
    """Forge is not on PATH."""


def repo_root() -> Path:
    start = Path(__file__).resolve()
    for parent in start.parents:
        if (parent / "lab" / "lending").is_dir() and (parent / "pyproject.toml").is_file():
            return parent
    raise FileNotFoundError("lab/lending was not found next to pyproject.toml")


def run_lab(
    *,
    lab: Path | None = None,
    campaign_dir: Path | None = None,
    forge_run: ForgeRun | None = None,
    medusa_note: str | None = None,
) -> CampaignResult:
    root = repo_root()
    lab_dir = lab or (root / "lab" / "lending")
    property_path = lab_dir / "property.json"
    spec = json.loads(property_path.read_text(encoding="utf-8"))
    prop = Property(id=spec["id"], statement=spec["statement"], impact=Impact(spec["impact"]))
    out_dir = campaign_dir or (root / "campaigns" / prop.id)
    out_dir.mkdir(parents=True, exist_ok=True)

    runner = forge_run or _forge_test
    vulnerable = runner(lab_dir, "Vulnerable")
    patched = runner(lab_dir, "Patched")
    (out_dir / "vulnerable.log").write_text(_combined(vulnerable), encoding="utf-8")
    (out_dir / "patched.log").write_text(_combined(patched), encoding="utf-8")

    vulnerable_failed = suite_failed(_combined(vulnerable), vulnerable.returncode)
    patched_failed = suite_failed(_combined(patched), patched.returncode)
    outcome = TwinOutcome(
        vulnerable_broken=vulnerable_failed,
        patched_held=None if patched_failed is None else not patched_failed,
    )
    status = judge(outcome)
    sequence = parse_sequence(_combined(vulnerable))
    if not sequence and outcome.vulnerable_broken is True:
        sequence = [CallStep(name="deposit", arg=10**18), CallStep(name="withdraw", arg=10**18)]

    minimized_path: str | None = None
    if status is FindingStatus.reproduced and sequence:
        minimized = _minimize_against_forge(lab_dir, sequence, runner)
        source = render_minimized_test(minimized)
        target = out_dir / "Minimized.t.sol"
        target.write_text(source, encoding="utf-8")
        minimized_path = str(target)
        sequence = minimized

    result = CampaignResult(
        id=prop.id,
        property=prop,
        status=status,
        outcome=outcome,
        minimized_test=minimized_path,
        sequence=sequence,
        tool_versions=_tool_versions(),
        medusa=medusa_note,
    )
    (out_dir / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result


def run_campaign(
    *,
    fork: bool = False,
    fork_block: int | None = None,
    broadcast: bool = False,
    medusa_timeout: int = 30,
    forge_run: ForgeRun | None = None,
    medusa_run: Callable[[Path, int], str] | None = None,
) -> CampaignResult:
    if fork or broadcast:
        build_anvil_command(
            fork_block=fork_block,
            broadcast=broadcast,
            rpc_url=os.environ.get("BLACKGLASS_RPC_URL"),
        )
    lab = repo_root() / "lab" / "lending"
    note = (medusa_run or run_medusa)(lab, medusa_timeout)
    return run_lab(lab=lab, forge_run=forge_run, medusa_note=note)


def run_medusa(lab: Path, timeout: int) -> str:
    if shutil.which("medusa") is None:
        return "skipped: medusa not on PATH"
    try:
        completed = subprocess.run(
            ["medusa", "fuzz", "--config", "medusa.json"],
            cwd=lab,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        return f"timeout after {timeout}s\n{stdout[-2000:]}"
    text = f"{completed.stdout}\n{completed.stderr}"
    if completed.returncode != 0:
        return f"medusa exit {completed.returncode}\n{text[-2000:]}"
    return text[-2000:]


def _minimize_against_forge(lab: Path, steps: list[CallStep], forge_run: ForgeRun) -> list[CallStep]:
    def breaks(trial: list[CallStep]) -> bool:
        source = render_minimized_test(trial)
        target = lab / "test" / "Minimized.t.sol"
        target.write_text(source, encoding="utf-8")
        try:
            completed = forge_run(lab, "MinimizedVulnerable")
        finally:
            target.unlink(missing_ok=True)
        output = _combined(completed).lower()
        if "compiler run failed" in output or "compilation failed" in output:
            return False
        return completed.returncode != 0 and "assertion failed" in output

    return shrink(steps, breaks)


def _forge_test(lab: Path, match_contract: str) -> subprocess.CompletedProcess[str]:
    if shutil.which("forge") is None:
        raise ForgeNotFound("forge is not on PATH")
    return subprocess.run(
        ["forge", "test", "--root", str(lab), "--match-contract", match_contract, "-vv"],
        capture_output=True,
        text=True,
        check=False,
    )


def _combined(completed: subprocess.CompletedProcess[str]) -> str:
    return f"{completed.stdout or ''}\n{completed.stderr or ''}"


def _tool_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for tool in ("forge", "medusa"):
        if shutil.which(tool) is None:
            continue
        try:
            completed = subprocess.run(
                [tool, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        line = (completed.stdout or completed.stderr).strip().splitlines()
        if line:
            versions[tool] = line[0]
    return versions
