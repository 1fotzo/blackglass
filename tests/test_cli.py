from typer.testing import CliRunner

from blackglass import __version__
from blackglass.banner import ONE_LINE
from blackglass.cli import app

runner = CliRunner()


def test_bare_command_prints_the_mark() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert ONE_LINE in result.output
    assert __version__ in result.output


def test_version_command_prints_the_mark_and_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert ONE_LINE in result.output
    assert __version__ in result.output


def test_quiet_flag_before_version() -> None:
    result = runner.invoke(app, ["--quiet", "version"])
    assert result.exit_code == 0
    assert result.output.splitlines()[0] == ONE_LINE


def test_quiet_flag_on_version() -> None:
    result = runner.invoke(app, ["version", "--quiet"])
    assert result.exit_code == 0
    assert result.output.splitlines()[0] == ONE_LINE
