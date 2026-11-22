import subprocess
from io import StringIO

from rich.console import Console

from blackglass import __version__
from blackglass.banner import ONE_LINE, lab_is_ready, print_banner

ANSI = __import__("re").compile(r"\x1b\[[0-9;]*m")


def _console(width: int, *, terminal: bool) -> tuple[Console, StringIO]:
    buf = StringIO()
    console = Console(
        file=buf,
        width=width,
        height=24,
        force_terminal=terminal,
        legacy_windows=False,
        color_system="truecolor" if terminal else None,
        highlight=False,
    )
    return console, buf


def _visible(text: str) -> str:
    return ANSI.sub("", text)


def test_quiet_prints_the_one_line_mark() -> None:
    console, buf = _console(100, terminal=True)
    print_banner(quiet=True, console=console, lab_ready=True)
    lines = [line for line in _visible(buf.getvalue()).splitlines() if line]
    assert lines[0] == ONE_LINE
    assert lines[1] == __version__


def test_pipe_prints_the_one_line_mark() -> None:
    console, buf = _console(100, terminal=False)
    print_banner(quiet=False, console=console, lab_ready=True)
    lines = [line for line in buf.getvalue().splitlines() if line]
    assert lines[0] == ONE_LINE
    assert "\x1b" not in buf.getvalue()


def test_no_color_prints_the_one_line_mark(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    console, buf = _console(100, terminal=True)
    print_banner(quiet=False, console=console, lab_ready=True)
    assert _visible(buf.getvalue()).splitlines()[0] == ONE_LINE
    assert "\x1b" not in buf.getvalue()


def test_narrow_terminal_collapses_to_the_one_line_mark(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    console, buf = _console(60, terminal=True)
    print_banner(quiet=False, console=console, lab_ready=True)
    visible = _visible(buf.getvalue())
    assert visible.splitlines()[0] == ONE_LINE
    assert "LAB READY" not in visible
    assert "WEB3 SECURITY" not in visible


def test_wide_terminal_draws_the_glass_plate(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    console, buf = _console(80, terminal=True)
    print_banner(quiet=False, console=console, lab_ready=False, detect_lab=lambda: True)
    visible = _visible(buf.getvalue())
    assert "BLACK" in visible
    assert "GLASS" in visible
    assert "WEB3 SECURITY" in visible
    assert "LAB ABSENT" in visible
    assert "█" in visible
    assert "LAB READY" not in visible
    assert visible.strip().splitlines()[-1] == __version__


def test_lab_ready_status_uses_the_passed_flag(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    console, buf = _console(80, terminal=True)
    print_banner(quiet=False, console=console, lab_ready=True)
    assert "LAB READY" in _visible(buf.getvalue())


def test_lab_is_ready_reads_docker_status() -> None:
    def ok(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0)

    def missing(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=[], returncode=1)

    def absent(*_args, **_kwargs):
        raise FileNotFoundError("docker")

    assert lab_is_ready(ok) is True
    assert lab_is_ready(missing) is False
    assert lab_is_ready(absent) is False
