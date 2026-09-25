"""Canonical evaluator output (overview §3.3)."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import model_validator

from permdiff.models.base import Frozen


class Effect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    ERROR = "error"


class ErrorKind(StrEnum):
    MISSING_CONTEXT = "missing_context"
    NONDETERMINISTIC = "nondeterministic"
    EVAL_ERROR = "eval_error"
    UNSUPPORTED = "unsupported"


EFFECT_ORDER: Final[dict[Effect, int]] = {
    Effect.DENY: 0,
    Effect.REQUIRE_APPROVAL: 1,
    Effect.ALLOW: 2,
}
"""Permissiveness rank. Moving up is widening; ``error`` is unranked."""

_COERCIBLE: Final[dict[str, Effect]] = {
    e.value: e for e in (Effect.ALLOW, Effect.DENY, Effect.REQUIRE_APPROVAL)
}


class Decision(Frozen):
    """One engine verdict for one call.

    ``effect == error`` always carries an ``error_kind``; other effects never do.
    """

    call_id: str
    effect: Effect
    error_kind: ErrorKind | None = None
    reasons: tuple[str, ...] = ()
    determining: tuple[str, ...] = ()
    engine: str

    @model_validator(mode="after")
    def _kind_matches_effect(self) -> Decision:
        if self.effect is Effect.ERROR and self.error_kind is None:
            msg = "error_kind is required when effect is 'error'"
            raise ValueError(msg)
        if self.effect is not Effect.ERROR and self.error_kind is not None:
            msg = f"error_kind must be null when effect is {self.effect.value!r}"
            raise ValueError(msg)
        return self

    @property
    def is_error(self) -> bool:
        return self.effect is Effect.ERROR

    @classmethod
    def error(cls, call_id: str, kind: ErrorKind, reason: str, *, engine: str) -> Decision:
        """Build a can't-evaluate decision with one reason."""
        return cls(
            call_id=call_id, effect=Effect.ERROR, error_kind=kind, reasons=(reason,), engine=engine
        )

    @classmethod
    def from_effect(
        cls,
        effect: Effect | str,
        *,
        call_id: str,
        engine: str,
        reasons: tuple[str, ...] = (),
        determining: tuple[str, ...] = (),
    ) -> Decision:
        """Coerce an engine's raw effect. Unknown strings become ``error/unsupported``."""
        resolved = effect if isinstance(effect, Effect) else _COERCIBLE.get(effect.strip().lower())
        if resolved is None or resolved is Effect.ERROR:
            return cls.error(
                call_id,
                ErrorKind.UNSUPPORTED,
                f"engine returned unknown effect {effect!r}",
                engine=engine,
            )
        return cls(
            call_id=call_id,
            effect=resolved,
            reasons=reasons,
            determining=determining,
            engine=engine,
        )
