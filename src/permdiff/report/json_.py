"""JSON reporter (FR-20): versioned envelope for scripts and the GitHub Action."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from permdiff.models import Counts, Frozen, ReportHeader, Transition, TransitionClass
from permdiff.report.exit_codes import FailOn, gate_reason
from permdiff.report.summary import SummaryRow
from permdiff.report.view import ReportView

REPORT_VERSION = "1"


class JsonGroup(Frozen):
    cls: TransitionClass
    key: dict[str, str]
    """``--group-by`` field → value."""
    label: str
    count: int
    effects: str
    reasons: tuple[str, ...]
    samples: tuple[Transition, ...]


class JsonReport(Frozen):
    """The ``--format json`` document. Field order is the wire order."""

    permdiff_report: Literal["1"] = "1"
    header: ReportHeader
    window: tuple[datetime, datetime] | None = None
    """Effective time window shown in the header (from filters, else the corpus extremes)."""
    exit_code: int
    fail_on: FailOn
    gate_reason: str
    counts: Counts
    summary: tuple[SummaryRow, ...]
    group_by: tuple[str, ...]
    groups: tuple[JsonGroup, ...]
    truncated_groups: int
    allow_widening: tuple[str, str] | None
    decisions: tuple[Transition, ...] | None = None
    """Every transition, only with ``--include-decisions``."""


def build_json_report(
    view: ReportView, *, exit_code: int, fail_on: FailOn, include_decisions: bool = False
) -> JsonReport:
    groups = tuple(
        JsonGroup(
            cls=g.cls,
            key=dict(g.key.parts),
            label=g.label,
            count=g.count,
            effects=g.effects,
            reasons=g.reasons,
            samples=g.samples,
        )
        for g in view.groups
    )
    return JsonReport(
        header=view.header,
        window=view.window,
        exit_code=exit_code,
        fail_on=fail_on,
        gate_reason=gate_reason(view, fail_on),
        counts=view.counts,
        summary=view.summary,
        group_by=view.group_by,
        groups=groups,
        truncated_groups=view.truncated_groups,
        allow_widening=view.allow_widening,
        decisions=view.transitions if include_decisions and view.transitions else None,
    )


def render_json(
    view: ReportView, *, exit_code: int, fail_on: FailOn, include_decisions: bool = False
) -> str:
    report = build_json_report(
        view, exit_code=exit_code, fail_on=fail_on, include_decisions=include_decisions
    )
    payload = report.model_dump(mode="json", exclude_none=False)
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"
