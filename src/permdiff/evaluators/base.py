"""Evaluator protocol (FR-9) and the determinism check shared by adapters (AC-12.3)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from permdiff.models import Decision, ErrorKind, ToolCall


@runtime_checkable
class PreparedPolicy(Protocol):
    """A policy compiled or loaded once per ref. ``close()`` releases resources."""

    @property
    def label(self) -> str: ...

    def close(self) -> None: ...


@runtime_checkable
class Evaluator(Protocol):
    """One policy engine. Third parties register via the ``permdiff.evaluators`` entry point.

    Optional attributes the report reads when present: ``label`` (header engine text,
    e.g. ``opa data.agent.authz.decision``) and ``undefined_policy`` (header note).
    """

    name: str

    def prepare(self, policy_dir: Path, *, label: str) -> PreparedPolicy:
        """Load the policy at ``policy_dir`` (one ref). Called once per ref."""
        ...

    def evaluate(self, prepared: PreparedPolicy, calls: Sequence[ToolCall]) -> tuple[Decision, ...]:
        """One ``Decision`` per call, in order, never raising for a single bad call."""
        ...


def evaluate_verified(
    evaluator: Evaluator, prepared: PreparedPolicy, calls: Sequence[ToolCall]
) -> tuple[Decision, ...]:
    """Evaluate twice; any call whose decision differs becomes ``error/nondeterministic``."""
    first = evaluator.evaluate(prepared, calls)
    second = evaluator.evaluate(prepared, calls)
    return tuple(_reconcile(a, b, evaluator.name) for a, b in zip(first, second, strict=True))


def _reconcile(a: Decision, b: Decision, engine: str) -> Decision:
    if a == b:
        return a
    reason = (
        f"decision differed between two runs: {_describe(a)} then {_describe(b)}; "
        "the policy reads something other than the trace"
    )
    return Decision.error(a.call_id, ErrorKind.NONDETERMINISTIC, reason, engine=engine)


def _describe(d: Decision) -> str:
    return f"{d.effect.value}/{d.error_kind.value}" if d.error_kind else d.effect.value
