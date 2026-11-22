import json
from pathlib import Path

from typer.testing import CliRunner

from blackglass.campaign.models import CampaignResult, FindingStatus, Impact, Property, TwinOutcome
from blackglass.cli import app
from blackglass.console import finish_auto, menu_text, open_console, run_auto
from blackglass.core.store import open_store

runner = CliRunner()


def _answers(*lines: str):
    pending = iter(lines)

    def read(_prompt: str) -> str:
        return next(pending)

    return read


def _result(root: Path) -> None:
    campaign = root / "campaigns" / "lab-lending-solvency"
    campaign.mkdir(parents=True)
    minimized = campaign / "Minimized.t.sol"
    minimized.write_text("contract Minimized {}\n", encoding="utf-8")
    payload = CampaignResult(
        id="lab-lending-solvency",
        property=Property(
            id="lab-lending-solvency",
            statement="Pool assets must cover recorded liabilities.",
            impact=Impact.funds,
        ),
        status=FindingStatus.reproduced,
        outcome=TwinOutcome(vulnerable_broken=True, patched_held=True),
        minimized_test=str(minimized),
    )
    (campaign / "result.json").write_text(payload.model_dump_json(indent=2), encoding="utf-8")


def test_menu_lists_live_modules_and_locked_ones() -> None:
    text = menu_text()
    assert "Lab" in text
    assert "Auto" in text
    assert "Recon" in text
    assert "not built" in text
    assert "Quit" in text


def test_locked_number_refuses_and_help_explains_auto(capsys) -> None:
    open_console(interactive=True, quiet=False, read=_answers("9", "8", "q"))
    output = capsys.readouterr().out
    assert "Recon is not built." in output
    assert "does not create a project" in output
    assert "select:" not in output


def test_campaign_does_not_start_without_a_yes(monkeypatch) -> None:
    def explode(*_args, **_kwargs) -> None:
        raise AssertionError("campaign started")

    monkeypatch.setattr("blackglass.console.do_campaign", explode)
    open_console(interactive=True, quiet=False, read=_answers("5", "n", "q"))


def test_pipe_does_not_open_the_menu(capsys) -> None:
    open_console(interactive=False, quiet=True)
    assert "later" not in capsys.readouterr().out


def test_help_command_lists_the_modules() -> None:
    result = runner.invoke(app, ["help"])
    assert result.exit_code == 0
    assert "Auto" in result.output
    assert "not built" in result.output


def test_option_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "auto" in result.output
    assert "glass-plate" in result.output


def test_auto_stops_before_the_lab_when_a_tool_is_missing() -> None:
    def refuse() -> CampaignResult:
        raise AssertionError("lab should not run")

    code = run_auto(yes=True, which=lambda _name: None, lab_run=refuse)
    assert code == 1


def test_auto_cancels_when_the_answer_is_no() -> None:
    code = run_auto(
        yes=False,
        read=_answers("n"),
        which=lambda _name: "tool",
        lab_run=lambda: (_ for _ in ()).throw(AssertionError("lab should not run")),
    )
    assert code == 0


def test_finish_auto_requires_an_open_project(tmp_path: Path) -> None:
    (tmp_path / "lab" / "lending").mkdir(parents=True)
    _result(tmp_path)
    error, report, _recommendation = finish_auto(tmp_path)
    assert error == "no project is open"
    assert report is None


def test_finish_auto_requires_scope(tmp_path: Path) -> None:
    (tmp_path / "lab" / "lending").mkdir(parents=True)
    store = open_store(tmp_path)
    store.create_project("lending")
    store.close()
    _result(tmp_path)
    error, report, _recommendation = finish_auto(tmp_path)
    assert error is not None
    assert "not in scope" in error
    assert report is None


def test_finish_auto_writes_the_report(tmp_path: Path) -> None:
    (tmp_path / "lab" / "lending").mkdir(parents=True)
    store = open_store(tmp_path)
    project_id = store.create_project("lending")
    store.grant_path(project_id, "lab/lending")
    store.close()
    _result(tmp_path)
    error, report, recommendation = finish_auto(tmp_path)
    assert error is None
    assert report is not None
    body = report.read_text(encoding="utf-8")
    assert "# lending" in body
    assert "## Reproduced" in body
    assert recommendation is not None
    assert "Retain the minimized test" in recommendation
    saved = json.loads((tmp_path / "campaigns" / "lab-lending-solvency" / "result.json").read_text(encoding="utf-8"))
    assert saved["status"] == "reproduced"
