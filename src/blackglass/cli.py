"""Command line entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from blackglass.chain.service import DEFAULT_WINDOW, do_recon_map, do_wallet_inspect
from blackglass.console import (
    SCOPE_PATH,
    do_campaign,
    do_corpus,
    do_lab,
    do_project_create,
    do_project_import,
    do_project_list,
    do_project_open,
    do_project_scope,
    do_report,
    do_status,
    open_console,
    run_auto,
)
from blackglass.console import HELP_TEXT as GUIDE_TEXT

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
    """Show the glass-plate banner. On a terminal, show the numbered console."""
    ctx.ensure_object(dict)
    ctx.obj["quiet"] = quiet
    if ctx.invoked_subcommand is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
        open_console(interactive=interactive, quiet=quiet)


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
    from blackglass.banner import print_banner

    print_banner(quiet=_quiet_from(ctx, quiet))


@app.command("auto")
def auto(
    yes: bool = typer.Option(False, "--yes", "-y", help="Run the playlist without asking."),
) -> None:
    """Run the lab, score the corpus, import, and write the report."""
    raise typer.Exit(code=run_auto(yes=yes))


@app.command("status")
def status() -> None:
    """Show the open project, the lab, and the last result."""
    do_status()


@app.command("help")
def guide() -> None:
    """Explain the numbered modules."""
    typer.echo(GUIDE_TEXT)


recon_app = typer.Typer(help="Pinned recon for one scoped address.")
wallet_app = typer.Typer(help="Wallet exposure for one scoped address.")
project_app = typer.Typer(help="Projects, scope, and campaign import.")
report_app = typer.Typer(help="Reports.")
lab_app = typer.Typer(help="Local twin harness.")
campaign_app = typer.Typer(help="Confirmation campaigns.")
corpus_app = typer.Typer(help="Corpus score.")
app.add_typer(recon_app, name="recon")
app.add_typer(wallet_app, name="wallet")
app.add_typer(project_app, name="project")
app.add_typer(report_app, name="report")
app.add_typer(lab_app, name="lab")
app.add_typer(campaign_app, name="campaign")
app.add_typer(corpus_app, name="corpus")


@recon_app.command("map")
def recon_map(
    chain_id: int = typer.Option(..., "--chain-id"),
    address: str = typer.Option(..., "--address"),
    block: int = typer.Option(..., "--block"),
    window: int = typer.Option(DEFAULT_WINDOW, "--window", help="Blocks before --block. Maximum 100000."),
) -> None:
    """Map one scoped address. Discovered neighbors are not granted."""
    do_recon_map(chain_id, address, block, window)


@wallet_app.command("inspect")
def wallet_inspect(
    chain_id: int = typer.Option(..., "--chain-id"),
    address: str = typer.Option(..., "--address"),
    block: int = typer.Option(..., "--block"),
    window: int = typer.Option(DEFAULT_WINDOW, "--window", help="Blocks before --block. Maximum 100000."),
) -> None:
    """Read balances, transfers, and approvals. Approvals stay observations."""
    do_wallet_inspect(chain_id, address, block, window)


@lab_app.command("test")
def lab_test() -> None:
    """Run the lending twins and apply the reproduced rule."""
    do_lab()


@campaign_app.command("run")
def campaign_run(
    fork: bool = typer.Option(False, "--fork", help="Require a pinned local Anvil fork."),
    fork_block: int | None = typer.Option(None, "--fork-block"),
    broadcast: bool = typer.Option(False, "--broadcast", help="Refused. The runner does not broadcast."),
    timeout: int = typer.Option(30, "--timeout", help="Seconds to allow Medusa to run."),
) -> None:
    """Run Medusa, then the lending twins."""
    do_campaign(fork=fork, fork_block=fork_block, broadcast=broadcast, timeout=timeout)


@corpus_app.command("score")
def corpus_score() -> None:
    """Print lending outcomes. Exit 1 if a patched twin broke."""
    do_corpus()


@project_app.command("create")
def project_create(
    name: str = typer.Argument(...),
    owner: str = typer.Option("", "--owner"),
) -> None:
    """Create a project and open it."""
    do_project_create(name, owner)


@project_app.command("list")
def project_list() -> None:
    """List projects."""
    do_project_list()


@project_app.command("open")
def project_open(name: str = typer.Argument(...)) -> None:
    """Make a project the current project."""
    do_project_open(name)


@project_app.command("scope")
def project_scope(
    path: str | None = typer.Option(None, "--path"),
    chain_id: int | None = typer.Option(None, "--chain-id"),
    address: str | None = typer.Option(None, "--address"),
) -> None:
    """Grant a repository path or a chain address."""
    do_project_scope(path=path, chain_id=chain_id, address=address)


@project_app.command("import")
def project_import(
    result: Path = typer.Argument(..., help="Campaign result.json"),
    path: str = typer.Option(SCOPE_PATH, "--path", help="In-scope path this result belongs to."),
) -> None:
    """Import a campaign. The path must already be in scope."""
    do_project_import(result, path)


@report_app.command("generate")
def report_generate(
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """Write a Markdown report with three labeled sections."""
    do_report(output)


if __name__ == "__main__":
    app()
