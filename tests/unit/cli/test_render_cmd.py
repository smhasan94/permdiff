from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from permdiff.cli.main import cli
from permdiff.cli.render import load_json_report, view_from_json
from permdiff.redact import Redactor
from permdiff.report import FailOn, build_view, gate, render_json, render_markdown, render_sarif
from tests.report_fixtures import FIXED_SALT, sample_report


def _json_file(tmp_path: Path, include_decisions: bool = True) -> Path:
    view = build_view(sample_report(), redactor=Redactor(salt=FIXED_SALT))
    text = render_json(
        view,
        exit_code=gate(view, FailOn.WIDEN),
        fail_on=FailOn.WIDEN,
        include_decisions=include_decisions,
    )
    path = tmp_path / "report.json"
    path.write_text(text, encoding="utf-8")
    return path


def test_view_round_trips_and_renders_identically(tmp_path: Path) -> None:
    direct = build_view(sample_report(), redactor=Redactor(salt=FIXED_SALT))
    report = load_json_report(_json_file(tmp_path))

    rebuilt = view_from_json(report)

    assert render_markdown(rebuilt, exit_code=2, fail_on=FailOn.WIDEN) == render_markdown(
        direct, exit_code=2, fail_on=FailOn.WIDEN
    )
    assert render_sarif(rebuilt, exit_code=2, fail_on=FailOn.WIDEN) == render_sarif(
        direct, exit_code=2, fail_on=FailOn.WIDEN
    )
    assert rebuilt.group_by == ("tool",)


def test_render_command_writes_each_format(tmp_path: Path) -> None:
    src = _json_file(tmp_path, include_decisions=False)
    runner = CliRunner()

    md = runner.invoke(cli, ["render", "--from-json", str(src)])
    sarif = runner.invoke(
        cli,
        [
            "render",
            "--from-json",
            str(src),
            "--format",
            "sarif",
            "--output",
            str(tmp_path / "r.sarif"),
        ],
    )
    term = runner.invoke(
        cli, ["render", "--from-json", str(src), "--format", "terminal", "--quiet"]
    )

    assert md.exit_code == 0, md.output
    assert md.stdout.startswith("<!-- permdiff -->\n")
    assert "**exit 2**" in md.stdout
    assert sarif.exit_code == 0
    assert json.loads((tmp_path / "r.sarif").read_text(encoding="utf-8"))["version"] == "2.1.0"
    assert term.exit_code == 0
    assert "exit 2 (widening found; --fail-on widen)" in term.stdout


def test_render_rejects_non_report_files(tmp_path: Path) -> None:
    bad = tmp_path / "x.json"
    bad.write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(cli, ["render", "--from-json", str(bad)])
    missing = CliRunner().invoke(cli, ["render", "--from-json", str(tmp_path / "nope.json")])

    assert result.exit_code == 1
    assert "--from-json" in result.stderr
    assert missing.exit_code == 1
    assert "cannot read" in missing.stderr
