from click.testing import CliRunner

from finplan.cli.main import cli
from finplan import __version__


def test_version():
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
