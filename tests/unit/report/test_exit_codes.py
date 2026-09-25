from __future__ import annotations

import pytest

from permdiff.models import Counts, Report, TransitionClass
from permdiff.report.exit_codes import EXIT_GATE, EXIT_OK, FailOn, gate, gate_reason
from tests.report_fixtures import sample_report


def _with_counts(**by_class: int) -> Report:
    base = sample_report()
    counts = Counts(
        evaluated=sum(by_class.values()),
        by_class={TransitionClass(k): v for k, v in by_class.items()},
    )
    return base.model_copy(update={"counts": counts})


@pytest.mark.parametrize(
    ("fail_on", "expected"),
    [
        (FailOn.WIDEN, EXIT_GATE),
        (FailOn.ANY_CHANGE, EXIT_GATE),
        (FailOn.CANT_EVALUATE, EXIT_GATE),
        (FailOn.NONE, EXIT_OK),
    ],
)
def test_gate_on_the_sample_report(fail_on: FailOn, expected: int) -> None:
    assert gate(sample_report(), fail_on) == expected


def test_widen_ignores_tightening_and_errors() -> None:
    report = _with_counts(tightening=2, cant_evaluate=1, unchanged=3)

    assert gate(report, FailOn.WIDEN) == EXIT_OK
    assert gate(report, FailOn.ANY_CHANGE) == EXIT_GATE
    assert gate(report, FailOn.CANT_EVALUATE) == EXIT_GATE


def test_cant_evaluate_ignores_widening() -> None:
    report = _with_counts(widening=5, unchanged=1)

    assert gate(report, FailOn.CANT_EVALUATE) == EXIT_OK


def test_attribution_change_alone_never_fails() -> None:
    report = _with_counts(attribution_change=4, unchanged=1)

    assert all(gate(report, f) == EXIT_OK for f in FailOn)


def test_allow_widening_waives_widening_only() -> None:
    only_widening = _with_counts(widening=2).model_copy(
        update={"allow_widening": ("ticket-123", "alice")}
    )
    mixed = _with_counts(widening=2, tightening=1).model_copy(
        update={"allow_widening": ("ticket-123", "alice")}
    )

    assert gate(only_widening, FailOn.WIDEN) == EXIT_OK
    assert gate(only_widening, FailOn.ANY_CHANGE) == EXIT_OK
    assert gate(mixed, FailOn.ANY_CHANGE) == EXIT_GATE
    assert gate_reason(only_widening, FailOn.WIDEN) == "widening allowed by alice: ticket-123"


def test_gate_reason_names_matched_classes_and_flag() -> None:
    report = _with_counts(widening=1, tightening=1, cant_evaluate=1)

    assert gate_reason(report, FailOn.WIDEN) == "widening found; --fail-on widen"
    assert gate_reason(report, FailOn.ANY_CHANGE) == (
        "widening, tightening, cant evaluate found; --fail-on any-change"
    )
    assert gate_reason(_with_counts(unchanged=3), FailOn.WIDEN) == "nothing matched --fail-on widen"
