from __future__ import annotations

import pytest
from pydantic import ValidationError

from permdiff.models import EFFECT_ORDER, Decision, Effect, ErrorKind


def test_effect_values_are_lowercase_strings() -> None:
    assert [e.value for e in Effect] == ["allow", "deny", "require_approval", "error"]
    assert [k.value for k in ErrorKind] == [
        "missing_context",
        "nondeterministic",
        "eval_error",
        "unsupported",
    ]


def test_effect_order_ranks_deny_below_approval_below_allow() -> None:
    assert EFFECT_ORDER[Effect.DENY] < EFFECT_ORDER[Effect.REQUIRE_APPROVAL]
    assert EFFECT_ORDER[Effect.REQUIRE_APPROVAL] < EFFECT_ORDER[Effect.ALLOW]
    assert Effect.ERROR not in EFFECT_ORDER


def test_error_effect_requires_error_kind() -> None:
    with pytest.raises(ValidationError, match="error_kind"):
        Decision(call_id="c", effect=Effect.ERROR, engine="x")


def test_non_error_effect_rejects_error_kind() -> None:
    with pytest.raises(ValidationError, match="error_kind"):
        Decision(call_id="c", effect=Effect.ALLOW, error_kind=ErrorKind.EVAL_ERROR, engine="x")


def test_error_constructor_sets_kind_and_reason() -> None:
    d = Decision.error("c", ErrorKind.MISSING_CONTEXT, "principal.department", engine="opa")

    assert d.effect is Effect.ERROR
    assert d.error_kind is ErrorKind.MISSING_CONTEXT
    assert d.reasons == ("principal.department",)
    assert d.determining == ()
    assert d.engine == "opa"
    assert d.is_error


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("allow", Effect.ALLOW),
        ("deny", Effect.DENY),
        ("require_approval", Effect.REQUIRE_APPROVAL),
        ("ALLOW", Effect.ALLOW),
        (" Deny ", Effect.DENY),
        (Effect.REQUIRE_APPROVAL, Effect.REQUIRE_APPROVAL),
    ],
)
def test_from_effect_coerces_strings(raw: str | Effect, expected: Effect) -> None:
    d = Decision.from_effect(raw, call_id="c", engine="py", reasons=("r",))

    assert d.effect is expected
    assert d.error_kind is None
    assert d.reasons == ("r",)
    assert not d.is_error


@pytest.mark.parametrize("raw", ["permit", "", "error", "yes"])
def test_from_effect_maps_unknown_strings_to_unsupported_error(raw: str) -> None:
    d = Decision.from_effect(raw, call_id="c", engine="py")

    assert d.effect is Effect.ERROR
    assert d.error_kind is ErrorKind.UNSUPPORTED
    assert repr(raw) in d.reasons[0]


def test_decision_json_round_trip() -> None:
    d = Decision(
        call_id="c",
        effect=Effect.REQUIRE_APPROVAL,
        reasons=("refund > 500",),
        determining=("policy/agent.rego:42",),
        engine="opa",
    )

    assert Decision.model_validate_json(d.model_dump_json()) == d


def test_decision_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="extra"):
        Decision.model_validate({"call_id": "c", "effect": "allow", "engine": "x", "bogus": 1})
