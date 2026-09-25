from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from permdiff.evaluators.python_callable import PythonCallableEvaluator
from permdiff.models import Effect, ErrorKind, ToolCall
from tests.fixtures.py_engine import rules

FIXTURES = "tests.fixtures.py_engine.rules"


def _call(call_id: str, tool: str, hour: int = 12) -> ToolCall:
    return ToolCall.model_validate(
        {
            "id": call_id,
            "timestamp": datetime(2026, 9, 20, hour, 0, tzinfo=UTC).isoformat(),
            "principal": {"id": "alice"},
            "agent": {"id": "bot"},
            "tool": {"name": tool},
        }
    )


def _evaluator(fn_name: str) -> PythonCallableEvaluator:
    return PythonCallableEvaluator(f"python:{FIXTURES}:{fn_name}", getattr(rules, fn_name))


def test_string_results_are_coerced_and_one_decision_per_call(tmp_path: Path) -> None:
    ev = _evaluator("allow_all")
    prepared = ev.prepare(tmp_path, label="base")

    decisions = ev.evaluate(prepared, [_call("a", "x"), _call("b", "y")])

    assert [d.call_id for d in decisions] == ["a", "b"]
    assert all(d.effect is Effect.ALLOW for d in decisions)
    assert all(d.engine == ev.name for d in decisions)
    assert prepared.label == "base"
    prepared.close()


def test_policy_dir_is_passed_to_the_callable(tmp_path: Path) -> None:
    (tmp_path / "rules.json").write_text(json.dumps({"x": "require_approval"}), encoding="utf-8")
    ev = _evaluator("by_table")

    decisions = ev.evaluate(ev.prepare(tmp_path, label="head"), [_call("a", "x"), _call("b", "y")])

    assert decisions[0].effect is Effect.REQUIRE_APPROVAL
    assert decisions[1].effect is Effect.DENY


def test_returned_decisions_get_call_id_and_engine_normalized(tmp_path: Path) -> None:
    ev = _evaluator("returns_decision")

    (d,) = ev.evaluate(ev.prepare(tmp_path, label="b"), [_call("real-id", "x")])

    assert d.call_id == "real-id"
    assert d.engine == ev.name
    assert d.effect is Effect.REQUIRE_APPROVAL
    assert d.reasons == ("amount over limit",)
    assert d.determining == ("rules.py:returns_decision",)


def test_exception_becomes_eval_error_and_does_not_abort_the_run(tmp_path: Path) -> None:
    ev = _evaluator("raises_for_tool")

    a, b, c = ev.evaluate(
        ev.prepare(tmp_path, label="b"), [_call("1", "ok"), _call("2", "boom"), _call("3", "ok")]
    )

    assert a.effect is Effect.ALLOW
    assert b.effect is Effect.ERROR
    assert b.error_kind is ErrorKind.EVAL_ERROR
    assert "RuntimeError: cannot evaluate boom" in b.reasons[0]
    assert c.effect is Effect.ALLOW


def test_non_string_non_decision_result_is_unsupported(tmp_path: Path) -> None:
    ev = _evaluator("returns_garbage")

    (d,) = ev.evaluate(ev.prepare(tmp_path, label="b"), [_call("1", "x")])

    assert d.effect is Effect.ERROR
    assert d.error_kind is ErrorKind.UNSUPPORTED
    assert "int" in d.reasons[0]


def test_unknown_effect_string_is_unsupported(tmp_path: Path) -> None:
    ev = PythonCallableEvaluator("python:x:y", lambda call, policy_dir: "permit")

    (d,) = ev.evaluate(ev.prepare(tmp_path, label="b"), [_call("1", "x")])

    assert d.error_kind is ErrorKind.UNSUPPORTED


@pytest.mark.parametrize(("hour", "effect"), [(12, Effect.ALLOW), (3, Effect.REQUIRE_APPROVAL)])
def test_trace_clock_rule_follows_call_timestamp(tmp_path: Path, hour: int, effect: Effect) -> None:
    ev = _evaluator("business_hours")

    (d,) = ev.evaluate(ev.prepare(tmp_path, label="b"), [_call("1", "x", hour=hour)])

    assert d.effect is effect


def test_prepared_from_another_evaluator_is_a_type_error(tmp_path: Path) -> None:
    class Other:
        label = "other"

        def close(self) -> None:
            return None

    ev = _evaluator("allow_all")

    with pytest.raises(TypeError, match="not from this evaluator"):
        ev.evaluate(Other(), [_call("1", "x")])
