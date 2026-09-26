"""HTML reporter (FR-L10): one self-contained document, inline CSS, no JavaScript.

Same content and redaction as the markdown PR comment; widening groups start expanded.
Deterministic for identical inputs (the golden test pins the output).
"""

from __future__ import annotations

import html
import json

from permdiff.models import Transition, TransitionClass
from permdiff.report.exit_codes import FailOn, gate_reason
from permdiff.report.grouping import Group
from permdiff.report.view import ReportView

_SHA_CHARS = 12
_CLASS_LABEL: dict[TransitionClass, str] = {
    TransitionClass.WIDENING: "widening",
    TransitionClass.TIGHTENING: "tightening",
    TransitionClass.CANT_EVALUATE: "can't evaluate",
    TransitionClass.ATTRIBUTION_CHANGE: "attribution change",
    TransitionClass.UNCHANGED: "unchanged",
}
_CSS = """
:root { color-scheme: light dark; --fg: #1f2328; --bg: #ffffff; --muted: #656d76;
  --line: #d0d7de; --warn-bg: #fff8c5; --warn-fg: #7d4e00; --code-bg: #f6f8fa; }
@media (prefers-color-scheme: dark) { :root { --fg: #e6edf3; --bg: #0d1117;
  --muted: #8b949e; --line: #30363d; --warn-bg: #3b2e00; --warn-fg: #f2cc60;
  --code-bg: #161b22; } }
body { margin: 0 auto; max-width: 60rem; padding: 1.5rem 1rem; color: var(--fg);
  background: var(--bg); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
h1 { font-size: 1.4rem; margin: 0 0 .25rem; } .meta { color: var(--muted); margin: 0 0 1rem; }
code { font: 0.9em ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--code-bg);
  padding: .1em .3em; border-radius: 4px; word-break: break-all; }
table { border-collapse: collapse; width: 100%; margin: .5rem 0 1rem; }
th, td { text-align: left; vertical-align: top; padding: .35rem .5rem;
  border-bottom: 1px solid var(--line); }
th { color: var(--muted); font-weight: 600; } td.n { text-align: right; }
details { border: 1px solid var(--line); border-radius: 6px; margin: .5rem 0;
  padding: .25rem .75rem; }
summary { cursor: pointer; font-weight: 600; padding: .25rem 0; }
.widening summary { color: var(--warn-fg); } .widening { background: var(--warn-bg); }
.reasons, .more { color: var(--muted); margin: .25rem 0 .5rem; }
footer { margin-top: 1.5rem; padding-top: .75rem; border-top: 1px solid var(--line);
  color: var(--muted); }
""".strip()


def _e(text: str) -> str:
    return html.escape(text, quote=True)


def _code(text: str) -> str:
    return f"<code>{_e(text)}</code>"


def _calls(n: int) -> str:
    return f"{n:,} call{'' if n == 1 else 's'}"


def _window(view: ReportView) -> str:
    if view.window is None:
        return ""
    start, end = view.window
    return f" · {start.date().isoformat()} → {end.date().isoformat()}"


def _header(view: ReportView) -> list[str]:
    h = view.header
    refs = [f"base {_code((h.base_sha or '-')[:_SHA_CHARS])}"]
    refs.append(
        "head <code>WORKTREE</code>"
        if h.is_worktree
        else f"head {_code((h.head_sha or '-')[:_SHA_CHARS])}"
    )
    refs.append(f"salt {_code(h.salt)}")
    if h.undefined_policy:
        refs.append(f"undefined = {_code(h.undefined_policy)}")
    return [
        f"<h1>permdiff: {_code(h.base_label)} → {_code(h.head_label)}</h1>",
        f'<p class="meta"><strong>{_calls(view.counts.evaluated)}</strong>{_e(_window(view))}'
        f" · policy {_code(h.policy_path)} · engine {_code(h.engine)}<br>"
        + " · ".join(refs)
        + "</p>",
    ]


def _summary(view: ReportView) -> list[str]:
    rows = []
    for row in view.summary:
        label = f"{_e(row.label)} ⚠ widening" if row.is_widening else _e(row.label)
        top = _code(row.detail) if row.detail else ""
        rows.append(f'<tr><td>{label}</td><td class="n">{row.count:,}</td><td>{top}</td></tr>')
    return [
        "<table><thead><tr><th>Transition</th><th>Count</th><th>Top</th></tr></thead>",
        "<tbody>",
        *rows,
        "</tbody></table>",
    ]


def _sample_row(t: Transition) -> str:
    args = "" if t.call.arguments is None else json.dumps(t.call.arguments, sort_keys=True)
    decision = t.base if (t.base.is_error and not t.head.is_error) else t.head
    reasons = "; ".join(decision.reasons)
    if decision.locations:
        where = ", ".join(decision.locations)
        reasons = f"{reasons} @ {where}" if reasons else f"@ {where}"
    return (
        f"<tr><td>{_code(t.call.id)}</td><td>{_code(t.call.principal.id)}</td>"
        f"<td>{_code(args) if args else ''}</td><td>{_e(reasons)}</td></tr>"
    )


def _group(group: Group) -> list[str]:
    widening = group.cls is TransitionClass.WIDENING
    title = (
        f"{'⚠ ' if widening else ''}{_e(_CLASS_LABEL[group.cls])} · {_code(group.label)} · "
        f"{_calls(group.count)} · {_e(group.effects)}"
    )
    lines = [
        f'<details{" open" if widening else ""} class="{"widening" if widening else "group"}">',
        f"<summary>{title}</summary>",
    ]
    if group.reasons:
        lines.append(f'<p class="reasons">Reasons: {_e("; ".join(group.reasons))}</p>')
    lines += [
        "<table><thead><tr><th>Call</th><th>Principal</th><th>Arguments</th><th>Reasons</th>"
        "</tr></thead><tbody>",
        *[_sample_row(t) for t in group.samples],
        "</tbody></table>",
    ]
    remaining = group.count - len(group.samples)
    if remaining:
        lines.append(f'<p class="more">…and {remaining:,} more</p>')
    lines.append("</details>")
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
        notes.append(f"allow-widening by {actor}: {reason}")
    lines = ["<footer>"]
    if notes:
        lines.append(f"<p>{_e(' · '.join(notes))}</p>")
    lines.append(f"<p><strong>exit {exit_code}</strong> ({_e(gate_reason(view, fail_on))})</p>")
    lines.append("</footer>")
    return lines


def render_html(view: ReportView, *, exit_code: int, fail_on: FailOn) -> str:
    """The whole document; the caller writes it to a file or stdout."""
    h = view.header
    body = _header(view) + _summary(view)
    for group in view.groups:
        body += _group(group)
    if view.truncated_groups:
        body.append(
            f'<p class="more">…{view.truncated_groups:,} more groups not shown '
            "(raise --max-groups)</p>"
        )
    body += _footer(view, exit_code=exit_code, fail_on=fail_on)
    title = _e(f"permdiff: {h.base_label} → {h.head_label}")
    return "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{title}</title>",
            f"<style>\n{_CSS}\n</style>",
            "</head>",
            "<body>",
            *body,
            "</body>",
            "</html>",
            "",
        ]
    )
