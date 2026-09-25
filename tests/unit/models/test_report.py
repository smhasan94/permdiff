from __future__ import annotations

import pytest
from pydantic import ValidationError

from permdiff.models import Counts, TransitionClass


def test_counts_default_to_zero() -> None:
    c = Counts()

    assert c.evaluated == 0
    assert c.of(TransitionClass.WIDENING) == 0


def test_counts_reject_by_class_that_does_not_sum_to_evaluated() -> None:
    with pytest.raises(ValidationError, match="sums to 2 but evaluated is 3"):
        Counts(evaluated=3, by_class={TransitionClass.WIDENING: 2})


def test_counts_accept_consistent_totals() -> None:
    c = Counts(
        imported=5,
        skipped=1,
        evaluated=4,
        by_class={TransitionClass.UNCHANGED: 3, TransitionClass.WIDENING: 1},
    )

    assert c.of(TransitionClass.WIDENING) == 1
    assert c.of(TransitionClass.TIGHTENING) == 0
