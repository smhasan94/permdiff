"""OPA result value → ``Decision`` (AC-10.4, AC-10.8, AC-10.10)."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from permdiff.models import Decision, Effect, ErrorKind

ENGINE_NAME = "opa"


class UndefinedPolicy(StrEnum):
    DENY = "deny"
    ERROR = "error"


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list | tuple):
        return tuple(str(v) for v in value)
    return (str(value),)


def to_decision(call_id: str, raw: Any, *, engine: str = ENGINE_NAME) -> Decision:
    """Map one result value. Objects carry ``effect`` plus optional reason(s) and rule(s)."""
    if isinstance(raw, bool):
        return Decision.from_effect(
            Effect.ALLOW if raw else Effect.DENY, call_id=call_id, engine=engine
        )
    if isinstance(raw, str):
        return Decision.from_effect(raw, call_id=call_id, engine=engine)
    if isinstance(raw, Mapping):
        effect = raw.get("effect")
        if not isinstance(effect, str):
            reason = f"result object has no string 'effect': {_short(raw)}"
            return Decision.error(call_id, ErrorKind.UNSUPPORTED, reason, engine=engine)
        reasons = _strings(raw.get("reasons")) or _strings(raw.get("reason"))
        rules = _strings(raw.get("rules")) or _strings(raw.get("rule"))
        return Decision.from_effect(
            effect, call_id=call_id, engine=engine, reasons=reasons, determining=rules
        )
    reason = f"result is {type(raw).__name__}, expected object, boolean, or effect string"
    return Decision.error(call_id, ErrorKind.UNSUPPORTED, reason, engine=engine)


def undefined_decision(
    call_id: str, policy: UndefinedPolicy, *, decision_path: str, engine: str = ENGINE_NAME
) -> Decision:
    """What an undefined rule means: configured default deny, or a can't-evaluate error."""
    if policy is UndefinedPolicy.DENY:
        return Decision(
            call_id=call_id,
            effect=Effect.DENY,
            reasons=(f"{decision_path} undefined (undefined = deny)",),
            engine=engine,
        )
    return Decision.error(
        call_id, ErrorKind.EVAL_ERROR, f"{decision_path} is undefined for this call", engine=engine
    )


def _short(value: Any, limit: int = 80) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"
