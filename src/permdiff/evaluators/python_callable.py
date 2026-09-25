"""Python callable evaluator (FR-12): ``--engine python:module.path:callable``.

WARNING: this imports and runs arbitrary code from the current Python
environment with the permissions of the user running permdiff. Only point it
at code you would run directly. Use OPA or Cedar for untrusted policy inputs.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from permdiff.evaluators.base import PreparedPolicy
from permdiff.models import Decision, ErrorKind, ToolCall

log = logging.getLogger(__name__)

PolicyCallable = Callable[[ToolCall, Path], Any]
"""``(call, policy_dir) -> Decision | str``; strings are ``allow|deny|require_approval``."""


@dataclass(frozen=True)
class PythonPrepared:
    label: str
    policy_dir: Path

    def close(self) -> None:
        return None


class PythonCallableEvaluator:
    """Calls a user function once per ``ToolCall``. One failing call never aborts the run."""

    def __init__(self, spec: str, fn: PolicyCallable) -> None:
        self.name = spec
        self._fn = fn

    def prepare(self, policy_dir: Path, *, label: str) -> PreparedPolicy:
        return PythonPrepared(label=label, policy_dir=policy_dir)

    def evaluate(self, prepared: PreparedPolicy, calls: Sequence[ToolCall]) -> tuple[Decision, ...]:
        if not isinstance(prepared, PythonPrepared):
            msg = f"{self.name}: prepared policy is not from this evaluator"
            raise TypeError(msg)
        return tuple(self._one(call, prepared.policy_dir) for call in calls)

    def _one(self, call: ToolCall, policy_dir: Path) -> Decision:
        try:
            result = self._fn(call, policy_dir)
        except Exception as exc:  # user code; the failure becomes a Decision
            log.debug("callable raised for call %s", call.id, exc_info=True)
            reason = f"{type(exc).__name__}: {exc}"
            return Decision.error(call.id, ErrorKind.EVAL_ERROR, reason, engine=self.name)
        return self._coerce(call.id, result)

    def _coerce(self, call_id: str, result: Any) -> Decision:
        if isinstance(result, Decision):
            return result.model_copy(update={"call_id": call_id, "engine": self.name})
        if isinstance(result, str):
            return Decision.from_effect(result, call_id=call_id, engine=self.name)
        reason = f"callable returned {type(result).__name__}, expected Decision or str"
        return Decision.error(call_id, ErrorKind.UNSUPPORTED, reason, engine=self.name)
