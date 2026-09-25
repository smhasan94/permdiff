"""Markdown reporter (FR-19): the PR comment. Deterministic for identical inputs."""

from __future__ import annotations

import html
import json

from permdiff.models import Transition, TransitionClass
from permdiff.report.exit_codes import FailOn, gate_reason
from permdiff.report.grouping import Group
from permdiff.report.view import ReportView

MARKER = "<!-- permdiff -->"
_SHA_CHARS = 12
_CLASS_ICON: dict[TransitionClass, str] = {
    TransitionClass.WIDENING: "⚠ widening",
    TransitionClass.TIGHTENING: "tightening",
    TransitionClass.CANT_EVALUATE: "can't evaluate",
    TransitionClass.ATTRIBUTION_CHANGE: "attribution change",
    TransitionClass.UNCHANGED: "unchanged",
}


def _cell(text: str) -> str:
    """Make arbitrary text safe inside a table cell."""
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _code(text: str) -> str:
    return "`" + text.replace("`", "'") + "`"


def _calls(n: int) -> str:
    return f"{n:,} call{'' if n == 1 else 's'}"


def _window(view: ReportView) -> str:
    if view.header.window is not None:
        start, end = view.header.window
    elif view.transitions:
        stamps = [t.call.timestamp for t in view.transitions]
        start, end = min(stamps), max(stamps)
    else:
        return ""
    return f" · {start.date().isoformat()} → {end.date().isoformat()}"


def _header(view: ReportView) -> list[str]:
    h = view.header
    refs = [f"base {_code((h.base_sha or '-')[:_SHA_CHARS])}"]
    refs.append(
        "head `WORKTREE`" if h.is_worktree else f"head {_code((h.head_sha or '-')[:_SHA_CHARS])}"
    )
    refs.append(f"salt {_code(h.salt)}")
    if h.undefined_policy:
        refs.append(f"undefined = {_code(h.undefined_policy)}")
    return [
        MARKER,
        f"## permdiff: {_code(h.base_label)} → {_code(h.head_label)}",
        "",
        f"**{_calls(view.counts.evaluated)}**{_window(view)} · policy {_code(h.policy_path)} · "
        f"engine {_code(h.engine)}  ",
        " · ".join(refs),
        "",
    ]


def _summary(view: ReportView) -> list[str]:
    lines = ["| Transition | Count | Top |", "|---|---:|---|"]
    for row in view.summary:
        label = f"{row.label} ⚠ widening" if row.is_widening else row.label
        top = _code(_cell(row.detail)) if row.detail else ""
        lines.append(f"| {label} | {row.count:,} | {top} |")
    lines.append("")
    return lines


def _sample_row(t: Transition) -> str:
    args = "" if t.call.arguments is None else json.dumps(t.call.arguments, sort_keys=True)
    decision = t.base if (t.base.is_error and not t.head.is_error) else t.head
    reasons = "; ".join(decision.reasons)
    return (
        f"| {_code(_cell(t.call.id))} | {_code(_cell(t.call.principal.id))} | "
        f"{_code(_cell(args)) if args else ''} | {_cell(reasons)} |"
    )


def _group(group: Group) -> list[str]:
    title = (
        f"{_CLASS_ICON[group.cls]} · <code>{html.escape(group.label)}</code> · "
        f"{_calls(group.count)} · {html.escape(group.effects)}"
    )
    lines = ["<details>", f"<summary>{title}</summary>", ""]
    if group.reasons:
        lines += ["Reasons: " + "; ".join(_cell(r) for r in group.reasons), ""]
    lines += ["| Call | Principal | Arguments | Reasons |", "|---|---|---|---|"]
    lines += [_sample_row(t) for t in group.samples]
    remaining = group.count - len(group.samples)
    if remaining:
        lines.append(f"\n…and {remaining:,} more")
    lines += ["", "</details>", ""]
    return lines


def _footer(view: ReportView, *, exit_code: int, fail_on: FailOn) -> list[str]:
    c = view.counts
    notes = []
    if c.skipped or c.filtered:
        parts = [f"imported {c.imported:,}"]
        if c.skipped:
            parts.append(f"skipped {c.skipped:,} malformed")
        if c.filtered:
            parts.append(f"filtered {c.filtered:,}")
        notes.append(", ".join(parts))
    if c.recorded_disagreements:
        notes.append(
            f"recorded decisions disagree with base on {_calls(c.recorded_disagreements)} "
            "(base ref may not be the deployed policy)"
        )
    if view.allow_widening is not None:
        reason, actor = view.allow_widening
        notes.append(f"allow-widening by {_cell(actor)}: {_cell(reason)}")
    lines = ["---"]
    if notes:
        lines.append(" · ".join(notes) + "  ")
    lines.append(f"**exit {exit_code}** ({gate_reason(view, fail_on)})")
    return lines


def render_markdown(view: ReportView, *, exit_code: int, fail_on: FailOn) -> str:
    """The PR comment. Starts with the marker the GitHub Action uses to find and update it."""
    lines = _header(view) + _summary(view)
    for group in view.groups:
        lines += _group(group)
    if view.truncated_groups:
        lines += [f"…{view.truncated_groups:,} more groups not shown (--max-groups)", ""]
    lines += _footer(view, exit_code=exit_code, fail_on=fail_on)
    return "\n".join(lines) + "\n"
