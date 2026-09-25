from __future__ import annotations

from typing import Any

import pytest

from permdiff.evaluators.opa.mapping import UndefinedPolicy, to_decision, undefined_decision
from permdiff.models import Effect, ErrorKind


@pytest.mark.parametrize(
    ("raw", "effect", "reasons", "rules"),
    [
        (True, Effect.ALLOW, (), ()),
        (False, Effect.DENY, (), ()),
        ("require_approval", Effect.REQUIRE_APPROVAL, (), ()),
        ({"effect": "allow"}, Effect.ALLOW, (), ()),
        ({"effect": "deny", "reason": "r", "rule": "p.rego:1"}, Effect.DENY, ("r",), ("p.rego:1",)),
        (
            {"effect": "require_approval", "reasons": ["a", "b"], "rules": ["x", "y"]},
            Effect.REQUIRE_APPROVAL,
            ("a", "b"),
            ("x", "y"),
        ),
        ({"effect": "ALLOW", "reasons": ["a"], "reason": "ignored"}, Effect.ALLOW, ("a",), ()),
    ],
)
def test_well_formed_results_map_to_effects(
    raw: Any, effect: Effect, reasons: tuple[str, ...], rules: tuple[str, ...]
) -> None:
    d = to_decision("c", raw)

    assert d.effect is effect
    assert d.reasons == reasons
    assert d.determining == rules
    assert d.engine == "opa"


@pytest.mark.parametrize(
    "raw", [{"effect": "permit"}, "permit", {"effect": 1}, {"reason": "no effect"}, 42, [1], None]
)
def test_unknown_or_malformed_results_are_unsupported_never_allow(raw: Any) -> None:
    d = to_decision("c", raw)

    assert d.effect is Effect.ERROR
    assert d.error_kind is ErrorKind.UNSUPPORTED
    assert d.reasons


def test_undefined_policy_deny_and_error() -> None:
    deny = undefined_decision("c", UndefinedPolicy.DENY, decision_path="data.x.y")
    err = undefined_decision("c", UndefinedPolicy.ERROR, decision_path="data.x.y")

    assert deny.effect is Effect.DENY
    assert "data.x.y undefined" in deny.reasons[0]
    assert err.error_kind is ErrorKind.EVAL_ERROR
    assert "data.x.y" in err.reasons[0]


@pytest.mark.parametrize(
    ("raw", "kind", "reason"),
    [
        (
            {"effect": "error", "kind": "missing_context", "reason": "principal.attrs.department"},
            ErrorKind.MISSING_CONTEXT,
            "principal.attrs.department",
        ),
        ({"effect": "error"}, ErrorKind.EVAL_ERROR, "policy returned effect 'error'"),
        (
            {"effect": "ERROR", "kind": "nondeterministic", "reasons": ["a", "b"]},
            ErrorKind.NONDETERMINISTIC,
            "a",
        ),
    ],
)
def test_policy_declared_errors_keep_their_kind(raw: Any, kind: ErrorKind, reason: str) -> None:
    d = to_decision("c", raw)

    assert d.effect is Effect.ERROR
    assert d.error_kind is kind
    assert d.reasons[0] == reason


def test_policy_declared_error_with_unknown_kind_is_unsupported() -> None:
    d = to_decision("c", {"effect": "error", "kind": "made_up"})

    assert d.error_kind is ErrorKind.UNSUPPORTED
    assert "made_up" in d.reasons[0]
