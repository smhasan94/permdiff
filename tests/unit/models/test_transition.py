from __future__ import annotations

import itertools

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from permdiff.models import Decision, Effect, ErrorKind, ToolCall, TransitionClass, classify
from permdiff.models.transition import CHANGE_CLASSES, Transition
from tests.unit.models.test_toolcall import MINIMAL

RANKED = (Effect.DENY, Effect.REQUIRE_APPROVAL, Effect.ALLOW)


def _decision(effect: Effect, determining: tuple[str, ...] = ("p1",)) -> Decision:
    if effect is Effect.ERROR:
        return Decision.error("c", ErrorKind.EVAL_ERROR, "x", engine="e")
    return Decision(call_id="c", effect=effect, determining=determining, engine="e")


def _expected(base: Effect, head: Effect) -> TransitionClass:
    if Effect.ERROR in (base, head):
        return TransitionClass.CANT_EVALUATE
    if RANKED.index(head) > RANKED.index(base):
        return TransitionClass.WIDENING
    if RANKED.index(head) < RANKED.index(base):
        return TransitionClass.TIGHTENING
    return TransitionClass.UNCHANGED


@pytest.mark.parametrize(("base", "head"), list(itertools.product(Effect, Effect)))
def test_all_sixteen_effect_pairs_classify_as_the_table_says(base: Effect, head: Effect) -> None:
    assert classify(_decision(base), _decision(head)) is _expected(base, head)


@pytest.mark.parametrize(
    ("base", "head"),
    [
        (Effect.DENY, Effect.ALLOW),
        (Effect.DENY, Effect.REQUIRE_APPROVAL),
        (Effect.REQUIRE_APPROVAL, Effect.ALLOW),
    ],
)
def test_every_move_up_the_order_is_widening(base: Effect, head: Effect) -> None:
    assert classify(_decision(base), _decision(head)) is TransitionClass.WIDENING
    assert classify(_decision(head), _decision(base)) is TransitionClass.TIGHTENING


@pytest.mark.parametrize("kind", list(ErrorKind))
def test_every_error_kind_on_either_side_is_cant_evaluate(kind: ErrorKind) -> None:
    err = Decision.error("c", kind, "x", engine="e")
    ok = _decision(Effect.ALLOW)

    assert classify(err, ok) is TransitionClass.CANT_EVALUATE
    assert classify(ok, err) is TransitionClass.CANT_EVALUATE
    assert classify(err, err) is TransitionClass.CANT_EVALUATE


def test_same_effect_with_different_determining_is_attribution_change() -> None:
    a = _decision(Effect.ALLOW, ("policy/a.rego:1",))
    b = _decision(Effect.ALLOW, ("policy/b.rego:9",))

    assert classify(a, b) is TransitionClass.ATTRIBUTION_CHANGE


def test_same_effect_different_reasons_only_is_unchanged() -> None:
    a = Decision(call_id="c", effect=Effect.DENY, reasons=("r1",), engine="e")
    b = Decision(call_id="c", effect=Effect.DENY, reasons=("r2",), engine="e")

    assert classify(a, b) is TransitionClass.UNCHANGED


def test_change_classes_exclude_unchanged_and_attribution() -> None:
    assert TransitionClass.UNCHANGED not in CHANGE_CLASSES
    assert TransitionClass.ATTRIBUTION_CHANGE not in CHANGE_CLASSES
    assert TransitionClass.WIDENING in CHANGE_CLASSES


@settings(max_examples=200, deadline=None)
@given(st.sampled_from(list(Effect)), st.sampled_from(list(Effect)))
def test_classification_is_total_and_single_valued(base: Effect, head: Effect) -> None:
    result = classify(_decision(base), _decision(head))

    assert result in TransitionClass
    assert (result is TransitionClass.UNCHANGED) == (base is head and base is not Effect.ERROR)


def test_transition_build_records_class() -> None:
    call = ToolCall.model_validate(MINIMAL)

    t = Transition.build(call, _decision(Effect.DENY), _decision(Effect.ALLOW))

    assert t.cls is TransitionClass.WIDENING
    assert t.call is call
