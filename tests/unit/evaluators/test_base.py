from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from permdiff.evaluators.base import Evaluator, evaluate_verified
from permdiff.evaluators.python_callable import PythonCallableEvaluator
from permdiff.models import Effect, ErrorKind, ToolCall
from tests.fixtures.py_engine import rules


def _call(call_id: str) -> ToolCall:
    return ToolCall.model_validate(
        {
            "id": call_id,
            "timestamp": datetime(2026, 9, 20, 12, tzinfo=UTC).isoformat(),
            "principal": {"id": "alice"},
            "agent": {"id": "bot"},
            "tool": {"name": "x"},
        }
    )


def test_python_evaluator_satisfies_protocol() -> None:
    ev = PythonCallableEvaluator("python:a:b", rules.allow_all)

    assert isinstance(ev, Evaluator)


def test_verified_evaluation_flags_calls_that_flip_between_runs(tmp_path: Path) -> None:
    ev = PythonCallableEvaluator("python:f:flip_flop", rules.flip_flop)
    prepared = ev.prepare(tmp_path, label="b")

    (d,) = evaluate_verified(ev, prepared, [_call("1")])

    assert d.effect is Effect.ERROR
    assert d.error_kind is ErrorKind.NONDETERMINISTIC
    assert "allow" in d.reasons[0]
    assert "deny" in d.reasons[0]


def test_verified_evaluation_keeps_stable_decisions(tmp_path: Path) -> None:
    ev = PythonCallableEvaluator("python:f:allow_all", rules.allow_all)
    prepared = ev.prepare(tmp_path, label="b")

    first, second = evaluate_verified(ev, prepared, [_call("1"), _call("2")])

    assert first.effect is Effect.ALLOW
    assert second.effect is Effect.ALLOW
    assert [d.call_id for d in (first, second)] == ["1", "2"]
