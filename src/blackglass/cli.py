"""Command line entrypoint."""

from __future__ import annotations

import typer

from blackglass.banner import print_banner

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
