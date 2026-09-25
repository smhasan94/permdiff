"""Transition classification (overview §3.3, FR-14)."""

from __future__ import annotations

from enum import StrEnum

from permdiff.models.base import Frozen
from permdiff.models.decision import EFFECT_ORDER, Decision
from permdiff.models.toolcall import ToolCall


class TransitionClass(StrEnum):
    WIDENING = "widening"
    TIGHTENING = "tightening"
    ATTRIBUTION_CHANGE = "attribution_change"
    CANT_EVALUATE = "cant_evaluate"
    UNCHANGED = "unchanged"


CHANGE_CLASSES: frozenset[TransitionClass] = frozenset(
    {TransitionClass.WIDENING, TransitionClass.TIGHTENING, TransitionClass.CANT_EVALUATE}
)
"""Classes that count as a change for ``--fail-on any-change``."""


def classify(base: Decision, head: Decision) -> TransitionClass:
    """Compare two decisions for the same call. Errors on either side never count as unchanged."""
    if base.is_error or head.is_error:
        return TransitionClass.CANT_EVALUATE
    before, after = EFFECT_ORDER[base.effect], EFFECT_ORDER[head.effect]
    if after > before:
        return TransitionClass.WIDENING
    if after < before:
        return TransitionClass.TIGHTENING
    if base.determining != head.determining:
        return TransitionClass.ATTRIBUTION_CHANGE
    return TransitionClass.UNCHANGED


class Transition(Frozen):
    call: ToolCall
    base: Decision
    head: Decision
    cls: TransitionClass

    @classmethod
    def build(cls, call: ToolCall, base: Decision, head: Decision) -> Transition:
        return cls(call=call, base=base, head=head, cls=classify(base, head))
