"""``permdiff render``: re-render a ``--format json`` report as markdown, SARIF, or terminal."""

from __future__ import annotations

from pathlib import Path

import click
from pydantic import ValidationError

from permdiff.cli._render import FORMATS
from permdiff.errors import ConfigError
from permdiff.report import JsonReport, ReportView, render_markdown, render_sarif, render_terminal
from permdiff.report.grouping import Group, GroupKey


def view_from_json(report: JsonReport) -> ReportView:
    """The reporters' input, rebuilt from the JSON envelope (samples only, unless decisions)."""
    groups = tuple(
        Group(
            key=GroupKey(cls=g.cls, parts=tuple(g.key.items())),
            count=g.count,
            samples=g.samples,
            reasons=g.reasons,
        )
        for g in report.groups
    )
    return ReportView(
        header=report.header,
        counts=report.counts,
        summary=report.summary,
        groups=groups,
        truncated_groups=report.truncated_groups,
        transitions=report.decisions or (),
        allow_widening=report.allow_widening,
        group_by=report.group_by,
        window=report.window,
    )


def load_json_report(path: Path) -> JsonReport:
    try:
        return JsonReport.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"--from-json {path}: cannot read: {exc.strerror or exc}"
        raise ConfigError(msg) from exc
    except (ValueError, ValidationError) as exc:
        msg = f"--from-json {path}: not a permdiff JSON report: {str(exc).splitlines()[0]}"
        raise ConfigError(msg) from exc


@click.command("render")
@click.option(
    "--from-json", "source", type=click.Path(path_type=Path, dir_okay=False), required=True
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice([f for f in FORMATS if f != "json"]),
    default="markdown",
    show_default=True,
)
@click.option("--output", type=click.Path(path_type=Path, dir_okay=False), default=None)
@click.option("--quiet", is_flag=True, help="Terminal: only the summary block.")
def render_cmd(source: Path, fmt: str, output: Path | None, quiet: bool) -> None:
    """Render a saved JSON report in another format. Exit code is the report's own."""
    report = load_json_report(source)
    view = view_from_json(report)
    if fmt == "markdown":
        text = render_markdown(view, exit_code=report.exit_code, fail_on=report.fail_on)
    elif fmt == "sarif":
        text = render_sarif(view, exit_code=report.exit_code, fail_on=report.fail_on)
    else:
        text = render_terminal(
            view, exit_code=report.exit_code, fail_on=report.fail_on, quiet=quiet
        )
    if output is not None:
        output.write_text(text, encoding="utf-8")
        click.echo(f"wrote {fmt} report to {output}", err=True)
    else:
        click.echo(text, nl=False)
