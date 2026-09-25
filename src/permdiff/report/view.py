"""``ReportView``: the redacted, grouped, sampled structure every reporter consumes."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from permdiff.models import Counts, Frozen, Report, ReportHeader, Transition
from permdiff.redact import Redactor
from permdiff.report.grouping import (
    DEFAULT_GROUP_BY,
    DEFAULT_MAX_GROUPS,
    DEFAULT_SAMPLES,
    Group,
    group_transitions,
    validate_group_by,
)
from permdiff.report.summary import SummaryRow, summary_rows


class ReportView(Frozen):
    header: ReportHeader
    counts: Counts
    summary: tuple[SummaryRow, ...]
    groups: tuple[Group, ...]
    truncated_groups: int
    """Groups dropped beyond ``max_groups`` (AC-19.3)."""
    transitions: tuple[Transition, ...]
    """Every transition, redacted, only when built with ``include_decisions``; else empty."""
    window: tuple[datetime, datetime] | None
    """Effective time window (from the header, else the corpus extremes)."""
    allow_widening: tuple[str, str] | None
    group_by: tuple[str, ...]


def build_view(
    report: Report,
    *,
    redactor: Redactor,
    by: Sequence[str] = DEFAULT_GROUP_BY,
    samples: int = DEFAULT_SAMPLES,
    max_groups: int = DEFAULT_MAX_GROUPS,
    show_attribution: bool = False,
    include_decisions: bool = False,
) -> ReportView:
    """One redaction path for every reporter (AC-17.5).

    Only sampled transitions are redacted and kept; grouping by principal uses the same
    salted hash the samples show, so counts stay exact without copying the corpus.
    """
    fields = validate_group_by(by)
    hash_principal = (
        (lambda pid: pid)
        if redactor.show_principal or redactor.is_identity
        else redactor.principal_hash
    )
    groups = group_transitions(
        report.transitions,
        by=fields,
        samples=samples,
        include_attribution=show_attribution,
        principal_key=hash_principal,
        sample_transform=redactor.transition,
    )
    kept = groups[: max(max_groups, 0)]
    return ReportView(
        header=report.header,
        counts=report.counts,
        summary=summary_rows(report),
        groups=kept,
        truncated_groups=len(groups) - len(kept),
        transitions=tuple(redactor.transition(t) for t in report.transitions)
        if include_decisions
        else (),
        allow_widening=report.allow_widening,
        group_by=fields,
        window=_window(report),
    )


def _window(report: Report) -> tuple[datetime, datetime] | None:
    if report.header.window is not None:
        return report.header.window
    if not report.transitions:
        return None
    stamps = [t.call.timestamp for t in report.transitions]
    return min(stamps), max(stamps)
