"""Replay a corpus against base and head policies (FR-13, FR-15)."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack

from permdiff.errors import EngineError
from permdiff.evaluators.base import Evaluator, PreparedPolicy, evaluate_verified
from permdiff.models import Decision, Frozen, ToolCall
from permdiff.models.report import Counts
from permdiff.models.transition import Transition, TransitionClass
from permdiff.policy.source import MaterializedPolicy

log = logging.getLogger(__name__)

EvaluateFn = Callable[[Evaluator, PreparedPolicy, Sequence[ToolCall]], tuple[Decision, ...]]


class ReplayResult(Frozen):
    transitions: tuple[Transition, ...]
    counts: Counts
    """Only ``evaluated``, ``by_class`` and ``recorded_disagreements`` are filled here."""


def replay(
    calls: Sequence[ToolCall],
    evaluator: Evaluator,
    base: MaterializedPolicy,
    head: MaterializedPolicy,
    *,
    concurrent: bool = True,
    verify_deterministic: bool = False,
) -> ReplayResult:
    """Evaluate every call at both refs and classify each pair. One transition per call."""
    evaluate: EvaluateFn = evaluate_verified if verify_deterministic else _plain_evaluate
    with ExitStack() as stack:
        prepared_base = evaluator.prepare(base.path, label=base.label)
        stack.callback(prepared_base.close)
        prepared_head = evaluator.prepare(head.path, label=head.label)
        stack.callback(prepared_head.close)
        base_decisions, head_decisions = _evaluate_both(
            evaluate, evaluator, prepared_base, prepared_head, calls, concurrent=concurrent
        )
    _check_alignment(calls, base_decisions, base.label, evaluator.name)
    _check_alignment(calls, head_decisions, head.label, evaluator.name)
    transitions = tuple(
        Transition.build(call, b, h)
        for call, b, h in zip(calls, base_decisions, head_decisions, strict=True)
    )
    return ReplayResult(transitions=transitions, counts=_count(transitions))


def _plain_evaluate(
    evaluator: Evaluator, prepared: PreparedPolicy, calls: Sequence[ToolCall]
) -> tuple[Decision, ...]:
    return evaluator.evaluate(prepared, calls)


def _evaluate_both(
    evaluate: EvaluateFn,
    evaluator: Evaluator,
    prepared_base: PreparedPolicy,
    prepared_head: PreparedPolicy,
    calls: Sequence[ToolCall],
    *,
    concurrent: bool,
) -> tuple[tuple[Decision, ...], tuple[Decision, ...]]:
    if not concurrent:
        return (
            evaluate(evaluator, prepared_base, calls),
            evaluate(evaluator, prepared_head, calls),
        )
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="permdiff-eval") as pool:
        base_future = pool.submit(evaluate, evaluator, prepared_base, calls)
        head_future = pool.submit(evaluate, evaluator, prepared_head, calls)
        return base_future.result(), head_future.result()


def _check_alignment(
    calls: Sequence[ToolCall], decisions: Sequence[Decision], label: str, engine: str
) -> None:
    if len(decisions) != len(calls):
        msg = (
            f"engine {engine} returned {len(decisions)} decisions for {len(calls)} calls "
            f"at {label}; adapters must return exactly one decision per call"
        )
        raise EngineError(msg)
    for call, decision in zip(calls, decisions, strict=True):
        if decision.call_id != call.id:
            msg = (
                f"engine {engine} returned decision for {decision.call_id!r} "
                f"where call {call.id!r} was expected at {label}"
            )
            raise EngineError(msg)


def _count(transitions: Sequence[Transition]) -> Counts:
    by_class: Counter[TransitionClass] = Counter(t.cls for t in transitions)
    disagreements = sum(
        1
        for t in transitions
        if t.call.recorded.effect is not None
        and not t.base.is_error
        and t.base.effect is not t.call.recorded.effect
    )
    return Counts(
        evaluated=len(transitions),
        by_class={cls: by_class[cls] for cls in TransitionClass if by_class[cls]},
        recorded_disagreements=disagreements,
    )
