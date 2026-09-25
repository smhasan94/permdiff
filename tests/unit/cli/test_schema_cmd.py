from __future__ import annotations

import json

from click.testing import CliRunner

from permdiff import schemas
from permdiff.cli.main import cli


def test_schema_command_prints_generated_schema() -> None:
    result = CliRunner().invoke(cli, ["schema", "toolcall"])

    assert result.exit_code == 0, result.output
    assert result.output == schemas.schema_text("toolcall")
    assert json.loads(result.output)["title"] == "ToolCall"


def test_schema_command_rejects_unknown_name() -> None:
    result = CliRunner().invoke(cli, ["schema", "nope"])

    assert result.exit_code == 2
    assert "toolcall" in result.output
