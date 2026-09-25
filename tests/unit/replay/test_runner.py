from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from permdiff.errors import EngineError
from permdiff.evaluators.base import PreparedPolicy
from permdiff.evaluators.python_callable import PythonCallableEvaluator
from permdiff.models import Decision, Effect, ErrorKind, ToolCall, TransitionClass
from permdiff.policy.source import GitRefSource, MaterializedPolicy
from permdiff.replay import replay
from tests.conftest import GitRepo
from tests.fixtures.py_engine import rules


def _call(call_id: str, tool: str, recorded: str | None = None) -> ToolCall:
    record: dict[str, Any] = {
        "id": call_id,
        "timestamp": datetime(2026, 9, 20, 12, tzinfo=UTC).isoformat(),
        "principal": {"id": "alice"},
        "agent": {"id": "bot"},
        "tool": {"name": tool},
    }
    if recorded:
        record["recorded"] = {"effect": recorded}
    return ToolCall.model_validate(record)


CALLS = [
    _call("1", "stripe.refund", recorded="deny"),  # deny -> require_approval: widening
    _call("2", "github.read", recorded="allow"),  # allow -> allow: unchanged
    _call("3", "x", recorded="allow"),  # deny -> allow: widening; recorded disagrees
    _call("4", "github.read"),  # unchanged, no recorded effect
]


@pytest.fixture
def refs(git_repo: GitRepo) -> Iterator[tuple[MaterializedPolicy, MaterializedPolicy]]:
    with (
        GitRefSource(git_repo.path, "v-base", "policy").materialize() as base,
        GitRefSource(git_repo.path, "HEAD", "policy").materialize() as head,
    ):
        yield base, head


@pytest.fixture
def evaluator() -> PythonCallableEvaluator:
    return PythonCallableEvaluator("python:fixtures:by_table", rules.by_table)


@pytest.mark.parametrize("concurrent", [True, False])
def test_replay_yields_one_transition_per_call_in_order(
    refs: tuple[MaterializedPolicy, MaterializedPolicy],
    evaluator: PythonCallableEvaluator,
    concurrent: bool,
) -> None:
    base, head = refs

    result = replay(CALLS, evaluator, base, head, concurrent=concurrent)

    assert [t.call.id for t in result.transitions] == ["1", "2", "3", "4"]
    assert [t.cls for t in result.transitions] == [
        TransitionClass.WIDENING,
        TransitionClass.UNCHANGED,
        TransitionClass.WIDENING,
        TransitionClass.UNCHANGED,
    ]
    assert result.transitions[0].base.effect is Effect.DENY
    assert result.transitions[0].head.effect is Effect.REQUIRE_APPROVAL


def test_counts_sum_and_recorded_disagreements(
    refs: tuple[MaterializedPolicy, MaterializedPolicy], evaluator: PythonCallableEvaluator
) -> None:
    base, head = refs

    counts = replay(CALLS, evaluator, base, head).counts

    assert counts.evaluated == 4
    assert sum(counts.by_class.values()) == 4
    assert counts.of(TransitionClass.WIDENING) == 2
    assert counts.of(TransitionClass.UNCHANGED) == 2
    assert counts.recorded_disagreements == 1  # call 3: recorded allow, base deny


def test_recorded_effect_never_influences_classification(
    refs: tuple[MaterializedPolicy, MaterializedPolicy], evaluator: PythonCallableEvaluator
) -> None:
    base, head = refs
    with_recorded = [_call("1", "stripe.refund", recorded="require_approval")]
    without = [_call("1", "stripe.refund")]

    a = replay(with_recorded, evaluator, base, head).transitions[0]
    b = replay(without, evaluator, base, head).transitions[0]

    assert a.cls is b.cls is TransitionClass.WIDENING


def test_empty_corpus_gives_empty_result(
    refs: tuple[MaterializedPolicy, MaterializedPolicy], evaluator: PythonCallableEvaluator
) -> None:
    base, head = refs

    result = replay([], evaluator, base, head)

    assert result.transitions == ()
    assert result.counts.evaluated == 0


def test_verify_deterministic_marks_flipping_calls(
    refs: tuple[MaterializedPolicy, MaterializedPolicy],
) -> None:
    base, head = refs
    flaky = PythonCallableEvaluator("python:fixtures:flip_flop", rules.flip_flop)

    (t,) = replay([_call("1", "x")], flaky, base, head, verify_deterministic=True).transitions

    assert t.cls is TransitionClass.CANT_EVALUATE
    assert ErrorKind.NONDETERMINISTIC in {t.base.error_kind, t.head.error_kind}


class _Prepared:
    def __init__(self, label: str, closed: list[str]) -> None:
        self.label = label
        self._closed = closed

    def close(self) -> None:
        self._closed.append(self.label)


class _MisbehavingEvaluator:
    name = "bad"

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.closed: list[str] = []

    def prepare(self, policy_dir: Path, *, label: str) -> PreparedPolicy:
        return _Prepared(label, self.closed)

    def evaluate(self, prepared: PreparedPolicy, calls: Sequence[ToolCall]) -> tuple[Decision, ...]:
        if self.mode == "short":
            return ()
        if self.mode == "wrong-id":
            return tuple(
                Decision(call_id="other", effect=Effect.ALLOW, engine=self.name) for _ in calls
            )
        raise RuntimeError("engine crashed")


@pytest.mark.parametrize(
    ("mode", "fragment"), [("short", "0 decisions for 1 calls"), ("wrong-id", "'other'")]
)
def test_misaligned_decisions_are_engine_errors(
    refs: tuple[MaterializedPolicy, MaterializedPolicy], mode: str, fragment: str
) -> None:
    base, head = refs
    bad = _MisbehavingEvaluator(mode)

    with pytest.raises(EngineError, match=fragment):
        replay([_call("1", "x")], bad, base, head)

    assert sorted(bad.closed) == ["HEAD", "v-base"]


def test_prepared_policies_are_closed_when_evaluation_raises(
    refs: tuple[MaterializedPolicy, MaterializedPolicy],
) -> None:
    base, head = refs
    bad = _MisbehavingEvaluator("crash")

    with pytest.raises(RuntimeError, match="engine crashed"):
        replay([_call("1", "x")], bad, base, head, concurrent=False)

    assert sorted(bad.closed) == ["HEAD", "v-base"]
