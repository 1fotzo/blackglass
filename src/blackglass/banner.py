"""Glass-plate startup mark.

One module owns the mark. Later report headers reuse ONE_LINE and FRACTURE_STYLE.
The fracture cyan is the only accent. Later severity emphasis uses that same color.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from subprocess import CompletedProcess

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from blackglass import __version__

ONE_LINE = "BLACKGLASS  ·  web3 security"
FRACTURE_STYLE = "cyan"
LAB_IMAGE = "blackglass-lab"
LAB_TOOLS = ("forge", "anvil", "medusa")
SLAB_MIN_WIDTH = 72
INNER_WIDTH = 52
_BG = "on grey11"

LabDetector = Callable[[], bool]


def lab_is_ready(
    run: Callable[..., CompletedProcess[str]] | None = None,
    which: Callable[[str], str | None] | None = None,
) -> bool:
    """Return whether a native lab toolchain or the blackglass-lab image is present."""
    finder = shutil.which if which is None else which
    if all(finder(tool) for tool in LAB_TOOLS):
        return True
    runner = run or subprocess.run
    try:
        completed = runner(
            ["docker", "image", "inspect", LAB_IMAGE],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def print_banner(
    *,
    quiet: bool = False,
    console: Console | None = None,
    lab_ready: bool | None = None,
    detect_lab: LabDetector = lab_is_ready,
) -> None:
    """Print the glass plate, or the one-line mark when the slab will not fit."""
    console = console or Console(highlight=False)
    plain = _use_plain(quiet, console)
    if plain:
        console.print(ONE_LINE, highlight=False, markup=False, soft_wrap=True)
    elif console.width < SLAB_MIN_WIDTH:
        console.print(_styled_one_line(), highlight=False, soft_wrap=True)
    else:
        ready = detect_lab() if lab_ready is None else lab_ready
        console.print(glass_plate(ready), highlight=False)
    if plain:
        console.print(__version__, highlight=False, markup=False)
    else:
        console.print(__version__, style="grey50", highlight=False)


def glass_plate(lab_ready: bool) -> Panel:
    """Build the obsidian slab. About 56 columns once the border is included."""
    body = Text()
    body.append_text(_content_line(_name(), _status(lab_ready)))
    body.append("\n")
    body.append_text(_content_line(_rule()))
    body.append("\n")
    body.append_text(_content_line(_subline()))
    return Panel(
        body,
        box=box.SQUARE,
        style=_BG,
        border_style="grey35",
        padding=(0, 1),
        expand=False,
    )


def _use_plain(quiet: bool, console: Console) -> bool:
    if quiet or "NO_COLOR" in os.environ or not console.is_terminal:
        return True
    return False


def _shard() -> Text:
    shard = Text()
    shard.append("░", style=f"grey19 {_BG}")
    shard.append("▒", style=f"grey35 {_BG}")
    shard.append("▓", style=f"grey58 {_BG}")
    shard.append("█", style=f"{FRACTURE_STYLE} {_BG}")
    return shard


def _pad(line: Text, width: int) -> Text:
    gap = width - line.cell_len
    if gap > 0:
        line.append(" " * gap, style=_BG)
    return line


def _content_line(body: Text, right: Text | None = None) -> Text:
    line = Text()
    line.append_text(_shard())
    line.append("  ", style=_BG)
    line.append_text(body)
    if right is not None:
        gap = INNER_WIDTH - line.cell_len - right.cell_len
        line.append(" " * max(gap, 1), style=_BG)
        line.append_text(right)
    return _pad(line, INNER_WIDTH)


def _name() -> Text:
    name = Text()
    name.append("BLACK", style=f"bold white {_BG}")
    name.append("GLASS", style=f"grey50 {_BG}")
    return name


def _status(lab_ready: bool) -> Text:
    label = "LAB READY" if lab_ready else "LAB ABSENT"
    return Text(label, style=f"grey62 {_BG}")


def _rule() -> Text:
    return Text("─" * (INNER_WIDTH - 6), style=f"grey35 {_BG}")


def _subline() -> Text:
    return Text("WEB3 SECURITY", style=f"grey70 {_BG}")


def _styled_one_line() -> Text:
    line = Text()
    line.append("BLACK", style="bold white")
    line.append("GLASS", style="grey50")
    line.append("  ·  ", style="grey35")
    line.append("web3 security", style="grey62")
    return line
