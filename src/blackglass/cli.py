"""Command line entrypoint."""

from __future__ import annotations

import typer

from blackglass.banner import print_banner
from blackglass.campaign.fork import ForkRefusal
from blackglass.campaign.models import FindingStatus
from blackglass.campaign.runner import ForgeNotFound, repo_root, run_campaign, run_lab
from blackglass.campaign.score import collect_rows, render_score

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


lab_app = typer.Typer(help="Local twin harness.")
campaign_app = typer.Typer(help="Confirmation campaigns.")
corpus_app = typer.Typer(help="Corpus score.")
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


if __name__ == "__main__":
    app()
