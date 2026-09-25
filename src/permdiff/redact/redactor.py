"""Redaction (FR-17). Applied once to a ``Report`` before any reporter sees it (AC-17.5).

``safe`` keeps structure and identifiers that policies key on (tool, agent,
resource type) and replaces everything that can carry PII: argument,
attribute and context values become ``<type:len>`` placeholders with keys
kept; principal ids become a salted SHA-256 prefix; resource ids are
placeholdered. Policy-authored text (``Decision.reasons`` and ``determining``)
is shown, but any trace value echoed into it (a policy that formats an
argument into its reason) is scrubbed and the text is length-capped, because
that text is policy-author controlled, not permdiff controlled. ``none`` is
the identity, for local use only.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from permdiff.models import Decision, Report, ToolCall, Transition

SALT_BYTES = 16
PRINCIPAL_PREFIX = "principal:"
PRINCIPAL_HASH_CHARS = 8
MAX_REASON_CHARS = 200
SCRUBBED = "<redacted>"
_MIN_SCRUB_LEN = 3
"""Trace values shorter than this are not scrubbed from reasons (too many false hits)."""


class RedactLevel(StrEnum):
    SAFE = "safe"
    NONE = "none"


def new_salt() -> bytes:
    """Fresh per-run salt so hashes correlate within one report, not across reports."""
    return secrets.token_bytes(SALT_BYTES)


_SCALAR_PLACEHOLDERS: tuple[tuple[type, str], ...] = (
    (bool, "<bool>"),  # before int: bool is an int subclass
    (int, "<int>"),
    (float, "<float>"),
)


def _scalar_placeholder(value: Any) -> str:
    if value is None:
        return "<null>"
    if isinstance(value, str):
        return f"<str:{len(value)}>"
    for kind, token in _SCALAR_PLACEHOLDERS:
        if isinstance(value, kind):
            return token
    return f"<{type(value).__name__}>"


def placeholder(value: Any) -> Any:
    """``<str:12>``, ``<int>``, ``<float>``, ``<bool>``, ``<null>``.

    Containers keep their shape and keys; only leaf values are replaced.
    """
    if isinstance(value, Mapping):
        return {str(k): placeholder(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [placeholder(v) for v in value]
    return _scalar_placeholder(value)


def _string_leaves(value: Any, out: list[str]) -> None:
    if isinstance(value, Mapping):
        for v in value.values():
            _string_leaves(v, out)
    elif isinstance(value, list | tuple):
        for v in value:
            _string_leaves(v, out)
    elif isinstance(value, str):
        out.append(value)
    elif isinstance(value, int | float) and not isinstance(value, bool):
        out.append(str(value))


def trace_values(call: ToolCall, *, skip_keys: frozenset[str] = frozenset()) -> tuple[str, ...]:
    """Every string or number in the call that redaction hides, longest first."""
    leaves: list[str] = [call.principal.id]
    if call.resource.id:
        leaves.append(call.resource.id)
    for source in (
        {k: v for k, v in (call.arguments or {}).items() if k not in skip_keys},
        call.principal.attrs,
        call.agent.attrs,
        call.resource.attrs,
        call.context,
    ):
        _string_leaves(source, leaves)
    return tuple(sorted({v for v in leaves if len(v) >= _MIN_SCRUB_LEN}, key=len, reverse=True))


def scrub_text(text: str, values: Sequence[str], *, limit: int = MAX_REASON_CHARS) -> str:
    """Replace echoed trace values with ``<redacted>`` and cap the length."""
    for value in values:
        if value in text:
            text = text.replace(value, SCRUBBED)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Redactor:
    """Returns redacted copies; never mutates its input."""

    def __init__(
        self,
        level: RedactLevel = RedactLevel.SAFE,
        salt: bytes | None = None,
        show_args: frozenset[str] = frozenset(),
        show_principal: bool = False,
    ) -> None:
        self.level = level
        self.salt = salt if salt is not None else new_salt()
        self.show_args = show_args
        self.show_principal = show_principal

    @property
    def salt_hex(self) -> str:
        return self.salt.hex()

    @property
    def is_identity(self) -> bool:
        return self.level is RedactLevel.NONE

    def principal_hash(self, principal_id: str) -> str:
        digest = hashlib.sha256(self.salt + principal_id.encode("utf-8")).hexdigest()
        return f"{PRINCIPAL_PREFIX}{digest[:PRINCIPAL_HASH_CHARS]}"

    def value(self, value: Any) -> Any:
        return value if self.level is RedactLevel.NONE else placeholder(value)

    def arguments(self, arguments: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
        if arguments is None or self.level is RedactLevel.NONE:
            return arguments
        return {k: (v if k in self.show_args else placeholder(v)) for k, v in arguments.items()}

    def call(self, call: ToolCall) -> ToolCall:
        if self.level is RedactLevel.NONE:
            return call
        principal_id = (
            call.principal.id if self.show_principal else self.principal_hash(call.principal.id)
        )
        return call.model_copy(
            update={
                "principal": call.principal.model_copy(
                    update={"id": principal_id, "attrs": placeholder(call.principal.attrs)}
                ),
                "agent": call.agent.model_copy(update={"attrs": placeholder(call.agent.attrs)}),
                "arguments": self.arguments(call.arguments),
                "resource": call.resource.model_copy(
                    update={
                        "id": None if call.resource.id is None else placeholder(call.resource.id),
                        "attrs": placeholder(call.resource.attrs),
                    }
                ),
                "context": placeholder(call.context),
            }
        )

    def transition(self, transition: Transition) -> Transition:
        """Redact the call, then scrub echoed trace values out of both decisions' text."""
        if self.level is RedactLevel.NONE:
            return transition
        values = trace_values(transition.call, skip_keys=self.show_args)
        return transition.model_copy(
            update={
                "call": self.call(transition.call),
                "base": self.decision(transition.base, values),
                "head": self.decision(transition.head, values),
            }
        )

    def decision(self, decision: Decision, values: Sequence[str]) -> Decision:
        return decision.model_copy(
            update={
                "reasons": tuple(scrub_text(r, values) for r in decision.reasons),
                "determining": tuple(scrub_text(d, values) for d in decision.determining),
            }
        )

    def report(self, report: Report) -> Report:
        if self.level is RedactLevel.NONE:
            return report
        return report.model_copy(
            update={"transitions": tuple(self.transition(t) for t in report.transitions)}
        )
