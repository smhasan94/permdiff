"""Summary rows shared by the terminal and markdown reporters (overview §0 block)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence

from permdiff.models import Effect, Frozen, Report, Transition, TransitionClass


class SummaryRow(Frozen):
    label: str
    count: int
    detail: str
    is_widening: bool = False


def _top(values: Sequence[str]) -> str:
    if not values:
        return ""
    (value, _n), *_ = Counter(values).most_common(1)
    return value


def _tools(ts: Sequence[Transition]) -> str:
    return _top([t.call.tool.name for t in ts])


def _error_detail(ts: Sequence[Transition]) -> str:
    reasons = []
    for t in ts:
        err = t.head if t.head.is_error else t.base
        kind = err.error_kind.value.replace("_", " ") if err.error_kind else "error"
        reasons.append(f"{kind}: {err.reasons[0]}" if err.reasons else kind)
    return _top(reasons)


_Selector = Callable[[Transition], bool]


def _row_specs() -> tuple[tuple[str, _Selector, bool], ...]:
    wid, tight = TransitionClass.WIDENING, TransitionClass.TIGHTENING
    return (
        ("newly DENIED", lambda t: t.cls is tight and t.head.effect is Effect.DENY, False),
        ("newly ALLOWED", lambda t: t.cls is wid and t.head.effect is Effect.ALLOW, True),
        (
            "now REQUIRE_APPROVAL",
            lambda t: t.head.effect is Effect.REQUIRE_APPROVAL and t.cls in (wid, tight),
            False,
        ),
        ("attribution changed", lambda t: t.cls is TransitionClass.ATTRIBUTION_CHANGE, False),
    )


def summary_rows(report: Report) -> tuple[SummaryRow, ...]:
    """Non-empty rows in display order, always ending with ``unchanged``."""
    ts = report.transitions
    rows: list[SummaryRow] = []
    for label, select, widening_only in _row_specs():
        matched = [t for t in ts if select(t)]
        if not matched:
            continue
        is_widening = widening_only or any(t.cls is TransitionClass.WIDENING for t in matched)
        rows.append(
            SummaryRow(
                label=label, count=len(matched), detail=_tools(matched), is_widening=is_widening
            )
        )
    errors = [t for t in ts if t.cls is TransitionClass.CANT_EVALUATE]
    if errors:
        rows.append(
            SummaryRow(label="can't evaluate", count=len(errors), detail=_error_detail(errors))
        )
    rows.append(
        SummaryRow(label="unchanged", count=report.counts.of(TransitionClass.UNCHANGED), detail="")
    )
    return tuple(rows)
