"""``ReportView``: the redacted, grouped, sampled structure every reporter consumes."""

from __future__ import annotations

from collections.abc import Sequence

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
    """Every transition, redacted; reporters that list decisions read this."""
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
) -> ReportView:
    """Redact once (AC-17.5), then group and sample on the redacted values."""
    redacted = redactor.report(report)
    fields = validate_group_by(by)
    groups = group_transitions(
        redacted.transitions, by=fields, samples=samples, include_attribution=show_attribution
    )
    kept = groups[: max(max_groups, 0)]
    return ReportView(
        header=redacted.header,
        counts=redacted.counts,
        summary=summary_rows(redacted),
        groups=kept,
        truncated_groups=len(groups) - len(kept),
        transitions=redacted.transitions,
        allow_widening=redacted.allow_widening,
        group_by=fields,
    )
