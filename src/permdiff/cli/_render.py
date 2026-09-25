"""Shared tail of ``diff`` and ``demo``: redact once, render, exit through the gate."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import click

from permdiff.errors import ConfigError
from permdiff.models import Report
from permdiff.redact import RedactLevel, Redactor
from permdiff.report import FailOn, ReportView, build_view, gate, render_markdown, render_terminal
from permdiff.report.grouping import DEFAULT_GROUP_BY, DEFAULT_MAX_GROUPS, DEFAULT_SAMPLES

FORMATS = ("terminal", "markdown")
PRINCIPAL_SHOWN_IN = frozenset({"terminal"})
"""Formats that print principal ids verbatim (overview §3.6); every other format hashes them."""


@dataclass(frozen=True)
class OutputOptions:
    fail_on: FailOn
    redact: RedactLevel
    show_args: frozenset[str]
    fmt: str = "terminal"
    samples: int = DEFAULT_SAMPLES
    group_by: tuple[str, ...] = DEFAULT_GROUP_BY
    max_groups: int = DEFAULT_MAX_GROUPS
    show_attribution: bool = False
    quiet: bool = False
    no_color: bool = False
    output: Path | None = None
    pr_comment: bool = False

    @property
    def show_principal(self) -> bool:
        return self.fmt in PRINCIPAL_SHOWN_IN

    def validated(self) -> OutputOptions:
        """``--pr-comment`` forces markdown and refuses ``--redact none`` (AC-17.3)."""
        if not self.pr_comment:
            return self
        if self.redact is RedactLevel.NONE:
            msg = "--pr-comment refuses --redact none: PR comments must never carry raw trace data"
            raise ConfigError(msg)
        return OutputOptions(**{**self.__dict__, "fmt": "markdown"})


def parse_show_args(text: str) -> frozenset[str]:
    return frozenset(k.strip() for k in text.split(",") if k.strip())


def use_color(no_color: bool) -> bool:
    return not no_color and not os.environ.get("NO_COLOR") and sys.stdout.isatty()


def emit_and_exit(ctx: click.Context, report: Report, opts: OutputOptions) -> None:
    """Redact with the report's own salt, print, and exit with the gate code."""
    redactor = Redactor(
        level=opts.redact,
        salt=bytes.fromhex(report.header.salt),
        show_args=opts.show_args,
        show_principal=opts.show_principal,
    )
    exit_code = gate(report, opts.fail_on)
    view = build_view(
        report,
        redactor=redactor,
        by=opts.group_by,
        samples=opts.samples,
        max_groups=opts.max_groups,
        show_attribution=opts.show_attribution,
    )
    text = render(view, opts, exit_code=exit_code)
    if opts.output is not None:
        opts.output.write_text(text, encoding="utf-8")
        click.echo(f"wrote {opts.fmt} report to {opts.output}", err=True)
    else:
        click.echo(text, nl=False)
    ctx.exit(exit_code)


def render(view: ReportView, opts: OutputOptions, *, exit_code: int) -> str:
    if opts.fmt == "markdown":
        return render_markdown(view, exit_code=exit_code, fail_on=opts.fail_on)
    return render_terminal(
        view,
        exit_code=exit_code,
        fail_on=opts.fail_on,
        quiet=opts.quiet,
        color=use_color(opts.no_color) and opts.output is None,
    )
