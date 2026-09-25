"""Terminal reporter (FR-18): summary block, then groups with samples."""

from __future__ import annotations

import json
from io import StringIO

from rich.console import Console
from rich.markup import escape

from permdiff.models import Transition, TransitionClass
from permdiff.report.exit_codes import EXIT_GATE, FailOn, gate_reason
from permdiff.report.grouping import Group
from permdiff.report.view import ReportView

DEFAULT_WIDTH = 100
_LABEL_WIDTH = 22
_COUNT_WIDTH = 7

CLASS_LABEL: dict[TransitionClass, str] = {
    TransitionClass.WIDENING: "widening",
    TransitionClass.TIGHTENING: "tightening",
    TransitionClass.CANT_EVALUATE: "can't evaluate",
    TransitionClass.ATTRIBUTION_CHANGE: "attribution change",
    TransitionClass.UNCHANGED: "unchanged",
}

_CLASS_STYLE: dict[TransitionClass, str] = {
    TransitionClass.WIDENING: "bold red",
    TransitionClass.TIGHTENING: "yellow",
    TransitionClass.CANT_EVALUATE: "magenta",
    TransitionClass.ATTRIBUTION_CHANGE: "cyan",
    TransitionClass.UNCHANGED: "dim",
}


def render_terminal(
    view: ReportView,
    *,
    exit_code: int,
    fail_on: FailOn,
    quiet: bool = False,
    color: bool = False,
    width: int = DEFAULT_WIDTH,
) -> str:
    """Render to a string. ``color`` false emits plain text (``--no-color`` / ``NO_COLOR``)."""
    console = Console(
        file=StringIO(),
        width=width,
        force_terminal=color,
        no_color=not color,
        color_system="standard" if color else None,
        highlight=False,
        soft_wrap=True,
    )
    _print_header(console, view)
    _print_summary(console, view)
    if not quiet:
        for group in view.groups:
            _print_group(console, group)
        if view.truncated_groups:
            console.print(f"\n[dim]… {view.truncated_groups:,} more groups (--max-groups)[/dim]")
    _print_footer(console, view, exit_code=exit_code, fail_on=fail_on)
    out = console.file
    assert isinstance(out, StringIO)  # noqa: S101  # console was built on a StringIO above
    return out.getvalue()


def _calls(n: int) -> str:
    return f"{n:,} call{'' if n == 1 else 's'}"


def _window(report: ReportView) -> str:
    if report.window is None:
        return ""
    start, end = report.window
    return f", {start.date().isoformat()} → {end.date().isoformat()}"


def _print_header(console: Console, report: ReportView) -> None:
    h = report.header
    console.print(
        f"[bold]permdiff:[/bold] {escape(h.base_label)} → {escape(h.head_label)}   "
        f"({_calls(report.counts.evaluated)}{_window(report)})"
    )
    parts = []
    if h.base_sha:
        parts.append(f"base {h.base_sha[:12]}")
    if h.is_worktree:
        parts.append("head WORKTREE")
    elif h.head_sha:
        parts.append(f"head {h.head_sha[:12]}")
    parts += [f"policy {escape(h.policy_path)}", f"engine {escape(h.engine)}"]
    console.print(f"[dim]  {'  '.join(parts)}[/dim]")


def _print_summary(console: Console, report: ReportView) -> None:
    for row in report.summary:
        style = "bold red" if row.is_widening else ("dim" if row.label == "unchanged" else "")
        label = f"{row.label:<{_LABEL_WIDTH}}"
        count = f"{row.count:>{_COUNT_WIDTH},}"
        detail = f"   {escape(row.detail)}" if row.detail else ""
        flag = "   ⚠ widening" if row.is_widening else ""
        line = f"  {label}{count}{detail}{flag}"
        console.print(f"[{style}]{line}[/{style}]" if style else line)


def _sample_line(t: Transition) -> str:
    args = "" if t.call.arguments is None else json.dumps(t.call.arguments, sort_keys=True)
    decision = t.head if t.cls is not TransitionClass.CANT_EVALUATE or t.head.is_error else t.base
    reasons = f"  [{'; '.join(decision.reasons)}]" if decision.reasons else ""
    return (
        f"    {escape(t.call.id)}  {escape(t.call.principal.id)}  {escape(args)}{escape(reasons)}"
    )


def _print_group(console: Console, group: Group) -> None:
    style = _CLASS_STYLE[group.cls]
    console.print()
    console.print(
        f"[{style}]{CLASS_LABEL[group.cls]}[/{style}]  [bold]{escape(group.label)}[/bold]  "
        f"({_calls(group.count)})   {escape(group.effects)}"
    )
    for sample in group.samples:
        console.print(_sample_line(sample))
    if group.count > len(group.samples):
        console.print(f"    [dim]… {group.count - len(group.samples):,} more[/dim]")


def _print_footer(console: Console, report: ReportView, *, exit_code: int, fail_on: FailOn) -> None:
    c = report.counts
    console.print()
    extras = []
    if c.skipped:
        extras.append(f"skipped {c.skipped:,} malformed")
    if c.filtered:
        extras.append(f"filtered {c.filtered:,}")
    if c.imported and (c.skipped or c.filtered):
        console.print(f"[dim]imported {c.imported:,}, {', '.join(extras)}[/dim]")
    if c.recorded_disagreements:
        console.print(
            f"[yellow]recorded decisions disagree with base on {_calls(c.recorded_disagreements)} "
            "(base ref may not be the deployed policy)[/yellow]"
        )
    if report.allow_widening is not None:
        reason, actor = report.allow_widening
        console.print(f"[yellow]allow-widening by {escape(actor)}: {escape(reason)}[/yellow]")
    style = "bold red" if exit_code == EXIT_GATE else "green"
    console.print(f"[{style}]exit {exit_code} ({escape(gate_reason(report, fail_on))})[/{style}]")
