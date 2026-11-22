"""Command line entrypoint."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import typer

from blackglass.banner import print_banner
from blackglass.campaign.fork import ForkRefusal
from blackglass.campaign.models import FindingStatus
from blackglass.campaign.runner import ForgeNotFound, repo_root, run_campaign, run_lab
from blackglass.campaign.score import collect_rows, render_score
from blackglass.core.config import ConfigError, load_config
from blackglass.core.importer import ImportError, import_campaign
from blackglass.core.report import render_report
from blackglass.core.scope import ScopeError, normalize_address, normalize_path
from blackglass.core.store import open_store

app = typer.Typer(
    name="blackglass",
    help="Web3 security confirmation engine.",
    invoke_without_command=True,
    no_args_is_help=False,
)


def _quiet_from(ctx: typer.Context, quiet: bool) -> bool:
    parent = ctx.parent
    parent_quiet = bool(parent is not None and parent.obj and parent.obj.get("quiet"))
    own_quiet = bool(ctx.obj and ctx.obj.get("quiet"))
    return quiet or parent_quiet or own_quiet


@app.callback()
def main(
    ctx: typer.Context,
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Print the one-line mark.",
    ),
) -> None:
    """Show the glass-plate banner when no command is given."""
    ctx.ensure_object(dict)
    ctx.obj["quiet"] = quiet
    if ctx.invoked_subcommand is None:
        print_banner(quiet=quiet)


@app.command()
def version(
    ctx: typer.Context,
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Print the one-line mark.",
    ),
) -> None:
    """Show the glass-plate banner and the version."""
    print_banner(quiet=_quiet_from(ctx, quiet))


project_app = typer.Typer(help="Projects, scope, and campaign import.")
report_app = typer.Typer(help="Reports.")
lab_app = typer.Typer(help="Local twin harness.")
campaign_app = typer.Typer(help="Confirmation campaigns.")
corpus_app = typer.Typer(help="Corpus score.")
app.add_typer(project_app, name="project")
app.add_typer(report_app, name="report")
app.add_typer(lab_app, name="lab")
app.add_typer(campaign_app, name="campaign")
app.add_typer(corpus_app, name="corpus")


def _emit(result) -> None:
    typer.echo(result.status.value)
    if result.outcome.patched_held is False:
        raise typer.Exit(code=1)
    if result.status is not FindingStatus.reproduced or not result.minimized_test:
        raise typer.Exit(code=1)


@lab_app.command("test")
def lab_test() -> None:
    """Run the lending twins and apply the reproduced rule."""
    try:
        result = run_lab()
    except ForgeNotFound as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _emit(result)


@campaign_app.command("run")
def campaign_run(
    fork: bool = typer.Option(False, "--fork", help="Require a pinned local Anvil fork."),
    fork_block: int | None = typer.Option(None, "--fork-block"),
    broadcast: bool = typer.Option(False, "--broadcast", help="Refused. The runner does not broadcast."),
    timeout: int = typer.Option(30, "--timeout", help="Seconds to allow Medusa to run."),
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


@corpus_app.command("score")
def corpus_score() -> None:
    """Print lending outcomes. Exit 1 if a patched twin broke."""
    root = repo_root()
    rows, code = collect_rows(root / "corpus" / "cases", root / "campaigns")
    typer.echo(render_score(rows))
    raise typer.Exit(code=code)


def _store():
    root = repo_root()
    config_path = root / "blackglass.toml"
    try:
        load_config(config_path)
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


@project_app.command("create")
def project_create(
    name: str = typer.Argument(...),
    owner: str = typer.Option("", "--owner"),
) -> None:
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


@project_app.command("list")
def project_list() -> None:
    """List projects."""
    _, store = _store()
    try:
        rows = store.list_projects()
    finally:
        store.close()
    for row in rows:
        typer.echo(row["name"])


@project_app.command("open")
def project_open(name: str = typer.Argument(...)) -> None:
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


@project_app.command("scope")
def project_scope(
    path: str | None = typer.Option(None, "--path"),
    chain_id: int | None = typer.Option(None, "--chain-id"),
    address: str | None = typer.Option(None, "--address"),
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


@project_app.command("import")
def project_import(
    result: Path = typer.Argument(..., help="Campaign result.json"),
    path: str = typer.Option("lab/lending", "--path", help="In-scope path this result belongs to."),
) -> None:
    """Import a campaign. The path must already be in scope."""
    root, store = _store()
    try:
        _require_current(store)
        imported = import_campaign(store, root, result, path)
    except (ImportError, ScopeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        store.close()
    typer.echo(imported.status.value)


@report_app.command("generate")
def report_generate(
    output: Path | None = typer.Option(None, "--output"),
) -> None:
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


if __name__ == "__main__":
    app()
