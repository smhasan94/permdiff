"""Shared tail of ``diff`` and ``demo``: redact once, render, exit through the gate."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import click

from permdiff.models import Report
from permdiff.redact import RedactLevel, Redactor
from permdiff.report import FailOn, gate, render_terminal
from permdiff.report.grouping import DEFAULT_SAMPLES

FORMATS = ("terminal",)


@dataclass(frozen=True)
class OutputOptions:
    fail_on: FailOn
    redact: RedactLevel
    show_args: frozenset[str]
    samples: int = DEFAULT_SAMPLES
    quiet: bool = False
    no_color: bool = False


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
        show_principal=True,
    )
    exit_code = gate(report, opts.fail_on)
    text = render_terminal(
        redactor.report(report),
        exit_code=exit_code,
        fail_on=opts.fail_on,
        quiet=opts.quiet,
        color=use_color(opts.no_color),
        samples=opts.samples,
    )
    click.echo(text, nl=False)
    ctx.exit(exit_code)
