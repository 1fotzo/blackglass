"""Numbered console. Live numbers call the commands that already exist."""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path

import typer

from blackglass.banner import LAB_TOOLS, lab_is_ready, print_banner
from blackglass.chain.service import do_recon_map, do_wallet_inspect
from blackglass.campaign.fork import ForkRefusal
from blackglass.campaign.models import CampaignResult, FindingStatus
from blackglass.campaign.runner import LAB_ID, ForgeNotFound, repo_root, run_campaign, run_lab
from blackglass.campaign.score import collect_rows, render_score
from blackglass.core.config import ConfigError, load_config
from blackglass.core.importer import ImportError as CampaignImportError
from blackglass.core.importer import import_campaign
from blackglass.core.report import render_report
from blackglass.core.scope import ScopeError, normalize_address, normalize_path
from blackglass.core.store import open_store

SCOPE_PATH = "lab/lending"
RESULT_PATH = Path("campaigns") / LAB_ID / "result.json"

LIVE: tuple[tuple[str, str, str], ...] = (
    ("1", "Lab", "run the lending twins"),
    ("2", "Corpus", "score the public cases"),
    ("3", "Project", "create, open, scope, import"),
    ("4", "Report", "write the markdown report"),
    ("5", "Campaign", "run Medusa, then the twins"),
    ("6", "Auto", "run the lab, score, import, report"),
    ("7", "Status", "project, lab, and last result"),
    ("8", "Help", "what each number does"),
    ("9", "Recon", "map a scoped address at a pinned block"),
    ("10", "Wallet", "balances, transfers, and approvals"),
)
LOCKED: tuple[tuple[str, str, str], ...] = (
    ("11", "Strike", "not built"),
    ("12", "Identity", "not built"),
    ("13", "Network", "not built"),
    ("14", "AI", "not built"),
)

HELP_TEXT = """
1  Lab       Runs the vulnerable pool and the patched pool. reproduced means the vulnerable pool broke and the patched pool held.
2  Corpus    Lists the ten public lending cases and the local campaign. Public cases stay inconclusive.
3  Project   Creates a project, opens it, grants a path, and imports a result. The path must be inside the repository.
4  Report    Writes the Markdown report for the open project.
5  Campaign  Runs Medusa, then the lending twins. Medusa does not set reproduced.
6  Auto      Checks the lab tools, runs the twins, scores the corpus, imports into the open project, and writes the report.
7  Status    Shows the open project, whether the lab tools are present, and the latest campaign result.
8  Help      Shows this text.
9  Recon     Maps one scoped address at a pinned block. Discovered neighbors are not granted.
10 Wallet    Reads balances, transfers, ERC-20 approvals, and Permit2 allowances. These stay observations.
11 Strike    Not built.

After a result, b returns to the numbered menu and q quits.

Strike, Identity, Network, and AI are listed and are not built.
Auto does not create a project, call a model, or broadcast. Recon does not broadcast or take a key.
The same actions are commands: blackglass lab test, blackglass corpus score, blackglass project, blackglass report generate, blackglass campaign run, blackglass auto, blackglass status, blackglass help, blackglass recon map, blackglass wallet inspect.
""".strip()

AUTO_STEPS = """
Auto runs these steps:
  1  Require Forge, Anvil, and Medusa
  2  Run the lending twins
  3  Score the corpus
  4  Import the result into the open project
  5  Write the report
""".strip()

PROJECT_MENU = """
  1  Create
  2  List
  3  Open
  4  Scope     grant a path
  5  Import    import a campaign result
  b  Back
""".strip()

Reader = Callable[[str], str]
Echo = Callable[..., None]


def menu_text() -> str:
    """Plain menu. Locked rows are visible and refuse to run."""
    lines = [""]
    for number, name, detail in LIVE:
        lines.append(f"  {number:>2}  {name:<10} {detail}")
    lines.append("")
    lines.append("  later")
    for number, name, detail in LOCKED:
        lines.append(f"  {number:>2}  {name:<10} {detail}")
    lines.append("")
    lines.append("   q  Quit")
    return "\n".join(lines)


BACK_TEXT = """
  b  Back to menu
  q  Quit
""".strip()


def open_console(*, interactive: bool, quiet: bool, read: Reader | None = None) -> None:
    """Print the banner. Offer the menu only on an interactive terminal."""
    print_banner(quiet=quiet)
    if quiet or not interactive:
        return
    reader = read or input
    numbers = {number for number, _, _ in LIVE + LOCKED}
    while True:
        typer.echo(menu_text())
        while True:
            try:
                choice = _resolve(reader("select: "))
            except (EOFError, KeyboardInterrupt):
                typer.echo("")
                return
            if choice in {"q", "quit"}:
                return
            if choice == "":
                continue
            if choice not in numbers:
                typer.echo("Choose a number, or q to quit.")
                continue
            break
        locked = _locked_name(choice)
        if locked is not None:
            typer.echo(f"{locked} is not built.")
        elif choice == "8":
            typer.echo(HELP_TEXT)
        else:
            try:
                _run_choice(choice, reader)
            except typer.Exit:
                pass
            except KeyboardInterrupt:
                typer.echo("")
        if _hold(reader) == "quit":
            return


def status_text(root: Path, *, lab_ready: bool) -> str:
    """One screen: open project, lab tools, latest campaign result."""
    project = "none"
    database = root / ".blackglass" / "project.db"
    if database.is_file():
        store = open_store(root)
        try:
            current = store.current()
            if current is not None:
                project = str(current["name"])
        finally:
            store.close()
    lab = "LAB READY" if lab_ready else "LAB ABSENT"
    return "\n".join(
        [
            f"project  {project}",
            f"lab      {lab}",
            _latest_result(root),
        ]
    )


def run_auto(
    *,
    yes: bool = False,
    read: Reader | None = None,
    echo: Echo | None = None,
    which: Callable[[str], str | None] | None = None,
    lab_run: Callable[..., CampaignResult] | None = None,
    score: Callable[[], tuple[str, int]] | None = None,
    finish: Callable[[], tuple[str | None, Path | None, str | None]] | None = None,
) -> int:
    """Run the fixed playlist. Stop at the first failure. Never create a project."""
    say = echo or typer.echo
    reader = read or input
    finder = shutil.which if which is None else which
    missing = [tool for tool in LAB_TOOLS if finder(tool) is None]
    if missing:
        for tool in missing:
            say(f"{tool} is not on PATH")
        return 1
    say(AUTO_STEPS)
    if not yes:
        try:
            answer = reader("run? [y/N]: ")
        except (EOFError, KeyboardInterrupt):
            say("")
            return 0
        if answer.strip().lower() not in {"y", "yes"}:
            say("cancelled")
            return 0
    try:
        result = (lab_run or run_lab)()
    except ForgeNotFound as exc:
        say(str(exc))
        return 1
    say(result.status.value)
    if result.outcome.patched_held is False or result.status is not FindingStatus.reproduced or not result.minimized_test:
        return 1
    text, code = (score or _score)()
    say(text)
    if code != 0:
        return 1
    error, report, recommendation = (finish or finish_auto)()
    if error is not None or report is None or recommendation is None:
        say(error or "the report was not written")
        return 1
    say(f"status  {result.status.value}")
    say(f"report  {report}")
    say(recommendation)
    return 0


def finish_auto(root: Path | None = None) -> tuple[str | None, Path | None, str | None]:
    """Import the lab result and write the report for the open project."""
    try:
        repo = repo_root() if root is None else root
    except FileNotFoundError as exc:
        return str(exc), None, None
    try:
        load_config(repo / "blackglass.toml")
    except ConfigError as exc:
        return str(exc), None, None
    result_path = repo / RESULT_PATH
    if not result_path.is_file():
        return f"{RESULT_PATH.as_posix()} was not found", None, None
    store = open_store(repo)
    try:
        project = store.current()
        if project is None:
            return "no project is open", None, None
        project_id = int(project["id"])
        if not store.in_scope_path(project_id, SCOPE_PATH):
            return (
                f"{SCOPE_PATH} is not in scope. Run: blackglass project scope --path {SCOPE_PATH}",
                None,
                None,
            )
        try:
            import_campaign(store, repo, result_path, SCOPE_PATH)
        except CampaignImportError as exc:
            return str(exc), None, None
        except ScopeError as exc:
            return str(exc), None, None
        body = render_report(store, project_id, str(project["name"]))
        destination = repo / ".blackglass" / "reports" / f"{project['name']}.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(body, encoding="utf-8")
        store.log(project_id, f"report generate {destination}")
    finally:
        store.close()
    recommendation = _recommendation(body)
    if recommendation is None:
        return "the report has no recommendation", None, None
    return None, destination, recommendation


def do_lab() -> None:
    """Run the lending twins and apply the reproduced rule."""
    try:
        result = run_lab()
    except ForgeNotFound as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _emit(result)


def do_campaign(
    *,
    fork: bool = False,
    fork_block: int | None = None,
    broadcast: bool = False,
    timeout: int = 30,
) -> None:
    """Run Medusa, then the lending twins."""
    try:
        result = run_campaign(
            fork=fork,
            fork_block=fork_block,
            broadcast=broadcast,
            medusa_timeout=timeout,
        )
    except (ForgeNotFound, ForkRefusal) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _emit(result)


def do_corpus() -> None:
    """Print lending outcomes. Exit 1 if a patched twin broke."""
    text, code = _score()
    typer.echo(text)
    raise typer.Exit(code=code)


def do_project_create(name: str, owner: str = "") -> None:
    """Create a project and open it."""
    _, store = _store()
    try:
        store.create_project(name, owner)
    except sqlite3.IntegrityError as exc:
        typer.echo(f"{name} already exists", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        store.close()
    typer.echo(name)


def do_project_list() -> None:
    """List projects."""
    _, store = _store()
    try:
        rows = store.list_projects()
    finally:
        store.close()
    for row in rows:
        typer.echo(row["name"])


def do_project_open(name: str) -> None:
    """Make a project the current project."""
    _, store = _store()
    try:
        store.open_project(name)
    except LookupError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        store.close()
    typer.echo(name)


def do_project_scope(
    path: str | None = None,
    chain_id: int | None = None,
    address: str | None = None,
) -> None:
    """Grant a repository path or a chain address."""
    root, store = _store()
    try:
        project = _require_current(store)
        project_id = int(project["id"])
        if path is not None:
            granted = normalize_path(root, path)
            store.grant_path(project_id, granted)
            typer.echo(granted)
            return
        if chain_id is None or address is None:
            typer.echo("pass --path, or both --chain-id and --address", err=True)
            raise typer.Exit(code=1)
        granted_address = normalize_address(address)
        store.grant_address(project_id, chain_id, granted_address)
        typer.echo(f"{chain_id} {granted_address}")
    except (ScopeError, ConfigError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        store.close()


def do_project_import(result: Path, path: str = SCOPE_PATH) -> None:
    """Import a campaign. The path must already be in scope."""
    root, store = _store()
    try:
        _require_current(store)
        imported = import_campaign(store, root, result, path)
    except (CampaignImportError, ScopeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        store.close()
    typer.echo(imported.status.value)


def do_report(output: Path | None = None) -> None:
    """Write a Markdown report with three labeled sections."""
    root, store = _store()
    try:
        project = _require_current(store)
        body = render_report(store, int(project["id"]), str(project["name"]))
        destination = output or (root / ".blackglass" / "reports" / f"{project['name']}.md")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(body, encoding="utf-8")
        store.log(int(project["id"]), f"report generate {destination}")
    finally:
        store.close()
    typer.echo(destination)


def do_status() -> None:
    """Show the open project, the lab, and the last result."""
    try:
        root = repo_root()
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(status_text(root, lab_ready=lab_is_ready()))


def _hold(read: Reader) -> str:
    """Keep the result on screen until the operator goes back or quits."""
    typer.echo("")
    typer.echo(BACK_TEXT)
    while True:
        try:
            answer = read("select: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            typer.echo("")
            return "quit"
        if answer in {"b", "back"}:
            return "menu"
        if answer in {"q", "quit"}:
            return "quit"
        typer.echo("Choose b or q.")


def _run_choice(choice: str, read: Reader) -> None:
    if choice == "1":
        do_lab()
    elif choice == "2":
        do_corpus()
    elif choice == "3":
        _project_menu(read)
    elif choice == "4":
        do_report()
    elif choice == "5":
        if _confirmed(read, "Run Medusa, then the lending twins? [y/N]: "):
            do_campaign()
    elif choice == "6":
        run_auto(yes=False, read=read)
    elif choice == "7":
        do_status()
    elif choice == "9":
        _run_chain(read, do_recon_map)
    elif choice == "10":
        _run_chain(read, do_wallet_inspect)


def _run_chain(read: Reader, action: Callable[..., None]) -> None:
    try:
        chain_raw = read("chain id: ").strip()
        address = read("address: ").strip()
        block_raw = read("block: ").strip()
        window_raw = read("window [5000]: ").strip() or "5000"
    except (EOFError, KeyboardInterrupt):
        typer.echo("")
        return
    if not chain_raw or not address or not block_raw:
        typer.echo("chain id, address, and block are required")
        return
    try:
        chain_id = int(chain_raw)
        block = int(block_raw)
        window = int(window_raw)
    except ValueError:
        typer.echo("chain id, block, and window must be integers")
        return
    action(chain_id, address, block, window)


def _project_menu(read: Reader) -> None:
    while True:
        typer.echo(PROJECT_MENU)
        try:
            choice = read("project: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            typer.echo("")
            return
        if choice in {"b", "back", "q", ""}:
            if choice == "":
                continue
            return
        try:
            if choice == "1":
                name = read("name: ").strip()
                if not name:
                    typer.echo("a name is required")
                    continue
                owner = read("owner: ").strip()
                do_project_create(name, owner)
            elif choice == "2":
                do_project_list()
            elif choice == "3":
                name = read("name: ").strip()
                if name:
                    do_project_open(name)
            elif choice == "4":
                path = read(f"path [{SCOPE_PATH}]: ").strip() or SCOPE_PATH
                do_project_scope(path=path)
            elif choice == "5":
                raw = read(f"result [{RESULT_PATH.as_posix()}]: ").strip() or RESULT_PATH.as_posix()
                do_project_import(Path(raw))
            else:
                typer.echo("Choose a number, or b to go back.")
        except typer.Exit:
            continue
        except KeyboardInterrupt:
            typer.echo("")
            return


def _confirmed(read: Reader, prompt: str) -> bool:
    try:
        answer = read(prompt)
    except (EOFError, KeyboardInterrupt):
        typer.echo("")
        return False
    return answer.strip().lower() in {"y", "yes"}


def _resolve(raw: str) -> str:
    choice = raw.strip().lower()
    if choice in {number for number, _, _ in LIVE + LOCKED}:
        return choice
    for number, name, _ in LIVE + LOCKED:
        if choice == name.lower():
            return number
    return choice


def _locked_name(choice: str) -> str | None:
    for number, name, _ in LOCKED:
        if choice == number:
            return name
    return None


def _recommendation(body: str) -> str | None:
    marker = "## Recommendations"
    if marker not in body:
        return None
    section = body.split(marker, maxsplit=1)[1]
    for line in section.splitlines():
        if line.startswith("- "):
            return line
    return None


def _emit(result: CampaignResult) -> None:
    typer.echo(result.status.value)
    if result.outcome.patched_held is False or result.status is not FindingStatus.reproduced or not result.minimized_test:
        raise typer.Exit(code=1)


def _score() -> tuple[str, int]:
    root = repo_root()
    rows, code = collect_rows(root / "corpus" / "cases", root / "campaigns")
    return render_score(rows), code


def _latest_result(root: Path) -> str:
    directory = root / "campaigns"
    if not directory.is_dir():
        return "result   none"
    paths = sorted(directory.glob("*/result.json"), key=lambda path: path.stat().st_mtime)
    if not paths:
        return "result   none"
    try:
        result = CampaignResult.model_validate(json.loads(paths[-1].read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError):
        return "result   unreadable"
    if result.outcome.patched_held is True:
        patched = "held"
    elif result.outcome.patched_held is False:
        patched = "broken"
    else:
        patched = "-"
    return f"result   {result.id}  {result.status.value}  {patched}"


def _store():
    root = repo_root()
    try:
        load_config(root / "blackglass.toml")
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    return root, open_store(root)


def _require_current(store):
    project = store.current()
    if project is None:
        typer.echo("no project is open", err=True)
        raise typer.Exit(code=1)
    return project
