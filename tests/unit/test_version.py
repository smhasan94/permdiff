from __future__ import annotations

import re

from click.testing import CliRunner

import permdiff
from permdiff.cli.main import cli


def test_version_is_pep440_like() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+)?", permdiff.__version__)


def test_cli_version_prints_version() -> None:
    # Arrange
    runner = CliRunner()

    # Act
    result = runner.invoke(cli, ["--version"])

    # Assert
    assert result.exit_code == 0
    assert permdiff.__version__ in result.output
