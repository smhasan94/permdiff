"""``OpaEvaluator``: one ``opa eval`` per ref over a generated shim (FR-10)."""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from permdiff import _proc
from permdiff.errors import EngineError
from permdiff.evaluators.base import PreparedPolicy
from permdiff.evaluators.opa.binary import resolve_binary
from permdiff.evaluators.opa.mapping import (
    ENGINE_NAME,
    UndefinedPolicy,
    to_decision,
    undefined_decision,
)
from permdiff.evaluators.opa.shim import (
    CASES_FILE,
    ND_MISS_PREFIX,
    RESULTS_RULE,
    SHIM_FILE,
    SHIM_PACKAGE,
    NdOverride,
    render_cases,
    render_shim,
    validate_decision_path,
)
from permdiff.models import Decision, ErrorKind, Frozen, ToolCall

log = logging.getLogger(__name__)

DEFAULT_DECISION = "data.agent.authz.decision"
MAX_BISECT_FAILURES = 64
"""After this many isolated builtin errors, remaining failing chunks are marked wholesale."""


class OpaOptions(Frozen):
    decision: str = DEFAULT_DECISION
    undefined: UndefinedPolicy = UndefinedPolicy.DENY
    opa_bin: Path | None = None
    v0_compatible: bool = False
    capabilities: Path | None = None
    nd_overrides: tuple[NdOverride, ...] = ()
    nd_data: Path | None = None


@dataclass(frozen=True)
class OpaPrepared:
    label: str
    policy_dir: Path
    compile_error: str | None = None
    denied_builtins: tuple[str, ...] = field(default_factory=tuple)

    def close(self) -> None:
        return None


class _BuiltinError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class OpaEvaluator:
    name = ENGINE_NAME

    def __init__(self, options: OpaOptions | None = None) -> None:
        self.options = options or OpaOptions()
        validate_decision_path(self.options.decision)
        self._bin: Path | None = None
        self._shim = render_shim(self.options.decision, nd_overrides=self.options.nd_overrides)

    @property
    def label(self) -> str:
        return f"{self.name} {self.options.decision}"

    @property
    def undefined_policy(self) -> str:
        return self.options.undefined.value

    @property
    def binary(self) -> Path:
        if self._bin is None:
            self._bin = resolve_binary(self.options.opa_bin)
        return self._bin

    def _common_flags(self) -> list[str]:
        flags: list[str] = []
        if self.options.v0_compatible:
            flags.append("--v0-compatible")
        if self.options.capabilities is not None:
            flags += ["--capabilities", str(self.options.capabilities)]
        return flags

    def prepare(self, policy_dir: Path, *, label: str) -> PreparedPolicy:
        """``opa check`` once per ref; a failure is recorded, not raised (every call errors)."""
        argv: list[str | Path] = [self.binary, "check", "--format", "json"]
        argv += [*self._common_flags(), policy_dir]
        result = _proc.run(argv)
        if result.ok:
            return OpaPrepared(label=label, policy_dir=policy_dir)
        message, denied = _compile_failure(result.stdout or result.stderr)
        log.warning("opa check failed at %s: %s", label, message)
        return OpaPrepared(
            label=label, policy_dir=policy_dir, compile_error=message, denied_builtins=denied
        )

    def evaluate(self, prepared: PreparedPolicy, calls: Sequence[ToolCall]) -> tuple[Decision, ...]:
        if not isinstance(prepared, OpaPrepared):
            msg = f"{self.name}: prepared policy is not from this evaluator"
            raise TypeError(msg)
        if prepared.compile_error is not None:
            return tuple(self._compile_error_decision(c.id, prepared) for c in calls)
        if not calls:
            return ()
        raw, failures = self._evaluate_with_bisect(prepared, calls)
        if not raw and not failures:
            log.warning(
                "%s produced no results at %s; check --decision",
                self.options.decision,
                prepared.label,
            )
        return tuple(self._decide(c, raw, failures) for c in calls)

    def _compile_error_decision(self, call_id: str, prepared: OpaPrepared) -> Decision:
        if prepared.denied_builtins:
            names = ", ".join(prepared.denied_builtins)
            reason = f"policy at {prepared.label} uses nondeterministic builtin {names}"
            return Decision.error(call_id, ErrorKind.NONDETERMINISTIC, reason, engine=self.name)
        reason = f"policy at {prepared.label} failed to compile: {prepared.compile_error}"
        return Decision.error(call_id, ErrorKind.EVAL_ERROR, reason, engine=self.name)

    def _decide(self, call: ToolCall, raw: dict[str, Any], failures: dict[str, str]) -> Decision:
        if call.id in failures:
            message = failures[call.id]
            if ND_MISS_PREFIX in message:
                key = message.split(ND_MISS_PREFIX, 1)[1].split('": invalid syntax')[0]
                reason = f"lookup missing from --nd-cache: {key}"
                return Decision.error(call.id, ErrorKind.NONDETERMINISTIC, reason, engine=self.name)
            return Decision.error(call.id, ErrorKind.EVAL_ERROR, message, engine=self.name)
        if call.id in raw:
            return to_decision(call.id, raw[call.id], engine=self.name)
        return undefined_decision(
            call.id, self.options.undefined, decision_path=self.options.decision, engine=self.name
        )

    def _evaluate_with_bisect(
        self, prepared: OpaPrepared, calls: Sequence[ToolCall]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Strict builtin errors abort a batch; split until each failing call is isolated."""
        raw: dict[str, Any] = {}
        failures: dict[str, str] = {}
        pending: list[Sequence[ToolCall]] = [calls]
        isolated = 0
        while pending:
            chunk = pending.pop()
            try:
                raw.update(self._run_batch(prepared, chunk))
            except _BuiltinError as exc:
                if len(chunk) == 1:
                    failures[chunk[0].id] = exc.message
                    isolated += 1
                elif isolated >= MAX_BISECT_FAILURES:
                    note = f"{exc.message} (bisect cap of {MAX_BISECT_FAILURES} reached)"
                    failures.update({c.id: note for c in chunk})
                else:
                    mid = len(chunk) // 2
                    pending += [chunk[:mid], chunk[mid:]]
        if failures:
            log.info("isolated %d builtin errors at %s", len(failures), prepared.label)
        return raw, failures

    def _run_batch(self, prepared: OpaPrepared, calls: Sequence[ToolCall]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="permdiff-opa-") as tmp:
            shim_path = Path(tmp) / SHIM_FILE
            cases_path = Path(tmp) / CASES_FILE
            shim_path.write_text(self._shim, encoding="utf-8")
            cases_path.write_bytes(render_cases(calls))
            argv: list[str | Path] = [
                self.binary,
                "eval",
                "--format",
                "json",
                "--strict-builtin-errors",
                *self._common_flags(),
                "-d",
                prepared.policy_dir,
                "-d",
                shim_path,
                "-d",
                cases_path,
            ]
            if self.options.nd_data is not None:
                argv += ["-d", self.options.nd_data]
            argv.append(f"data.{SHIM_PACKAGE}.{RESULTS_RULE}")
            result = _proc.run(argv)
        return _parse_eval_output(result, label=prepared.label)


def _parse_eval_output(result: _proc.ProcResult, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(result.stdout) if result.stdout.strip() else {}
    except ValueError as exc:
        msg = f"opa eval at {label} returned invalid JSON: {result.stderr.strip()[:300]}"
        raise EngineError(msg) from exc
    errors = payload.get("errors")
    if errors:
        first = errors[0]
        message = str(first.get("message", "unknown error"))
        if first.get("code") == "eval_builtin_error":
            raise _BuiltinError(message)
        msg = f"opa eval failed at {label}: {message}"
        raise EngineError(msg)
    if not result.ok:
        msg = (
            f"opa eval failed at {label} (exit {result.returncode}): {result.stderr.strip()[:300]}"
        )
        raise EngineError(msg)
    try:
        value = payload["result"][0]["expressions"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return {}
    return {str(item["id"]): item["value"] for item in value}


def _compile_failure(text: str) -> tuple[str, tuple[str, ...]]:
    """Message and any builtins the policy uses that the capabilities file omits."""
    try:
        payload = json.loads(text)
        errors = payload.get("errors") or []
        messages = [str(e.get("message", "")) for e in errors]
    except ValueError:
        messages = [text.strip()]
    denied = tuple(
        sorted(
            {
                m.removeprefix("undefined function ")
                for m in messages
                if m.startswith("undefined function ")
            }
        )
    )
    return "; ".join(m for m in messages if m) or "unknown compile error", denied
