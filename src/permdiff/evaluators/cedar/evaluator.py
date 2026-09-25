"""``CedarEvaluator`` (FR-11): batch authorization with approval via annotation."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cedarpy

from permdiff.evaluators.base import PreparedPolicy
from permdiff.evaluators.cedar.loader import PolicyBundle, PolicyMeta, load_bundle, validate
from permdiff.evaluators.cedar.request import (
    MissingTemplateValue,
    build_request,
    check_template,
    missing_name,
)
from pydantic import model_validator

from permdiff.models import Decision, Effect, ErrorKind, Frozen, ToolCall

log = logging.getLogger(__name__)

ENGINE_NAME = "cedar"
DEFAULT_PRINCIPAL = 'User::"{principal.id}"'
DEFAULT_ACTION = 'Action::"{tool.name}"'
DEFAULT_RESOURCE = 'Resource::"{resource.id}"'
BATCH_SIZE = 20_000


class CedarOptions(Frozen):
    principal: str = DEFAULT_PRINCIPAL
    action: str = DEFAULT_ACTION
    resource: str = DEFAULT_RESOURCE
    approval_annotation: str = "require_approval"
    now_key: str = "now"

    @model_validator(mode="after")
    def _templates_use_known_fields(self) -> CedarOptions:
        for name in ("principal", "action", "resource"):
            check_template(getattr(self, name))  # raises ValueError naming the field
        return self


@dataclass(frozen=True)
class CedarPrepared:
    label: str
    policy_dir: Path
    bundle: PolicyBundle | None = None
    compile_error: str | None = None
    files: tuple[str, ...] = field(default_factory=tuple)

    def close(self) -> None:
        return None


class CedarEvaluator:
    name = ENGINE_NAME

    def __init__(self, options: CedarOptions | None = None) -> None:
        self.options = options or CedarOptions()

    @property
    def label(self) -> str:
        return f"{self.name} {self.options.action}"

    def prepare(self, policy_dir: Path, *, label: str) -> PreparedPolicy:
        """Load and validate once per ref; a failure is recorded so every call reports it."""
        try:
            bundle = load_bundle(policy_dir)
        except Exception as exc:  # any loader failure is a compile error for this ref
            log.warning("cedar load failed at %s: %s", label, exc)
            return CedarPrepared(label=label, policy_dir=policy_dir, compile_error=str(exc))
        error = validate(bundle)
        if error:
            log.warning("cedar validation failed at %s: %s", label, error)
        return CedarPrepared(
            label=label,
            policy_dir=policy_dir,
            bundle=bundle,
            compile_error=error,
            files=bundle.files,
        )

    def evaluate(self, prepared: PreparedPolicy, calls: Sequence[ToolCall]) -> tuple[Decision, ...]:
        if not isinstance(prepared, CedarPrepared):
            msg = f"{self.name}: prepared policy is not from this evaluator"
            raise TypeError(msg)
        if prepared.compile_error is not None or prepared.bundle is None:
            reason = f"policy at {prepared.label} failed to load: {prepared.compile_error}"
            return tuple(
                Decision.error(c.id, ErrorKind.EVAL_ERROR, reason, engine=self.name) for c in calls
            )
        decisions: list[Decision | None] = [None] * len(calls)
        requests: list[dict[str, Any]] = []
        positions: list[int] = []
        for index, call in enumerate(calls):
            try:
                requests.append(self._request(call))
            except MissingTemplateValue as exc:
                reason = f"request template needs {exc.path}, which the trace lacks"
                decisions[index] = Decision.error(
                    call.id, ErrorKind.MISSING_CONTEXT, reason, engine=self.name
                )
                continue
            positions.append(index)
        bundle = prepared.bundle
        for start in range(0, len(requests), BATCH_SIZE):
            chunk = requests[start : start + BATCH_SIZE]
            results = cedarpy.is_authorized_batch(chunk, bundle.policies, list(bundle.entities))
            for offset, result in enumerate(results):
                index = positions[start + offset]
                decisions[index] = self._decision(calls[index].id, result, bundle)
        return tuple(d for d in decisions if d is not None)

    def _request(self, call: ToolCall) -> dict[str, Any]:
        o = self.options
        return build_request(
            call, principal=o.principal, action=o.action, resource=o.resource, now_key=o.now_key
        )

    def _decision(self, call_id: str, result: Any, bundle: PolicyBundle) -> Decision:
        reasons = [str(r) for r in result.diagnostics.reasons]
        errors = [str(e) for e in result.diagnostics.errors]
        metas = [
            bundle.meta.get(r) or PolicyMeta(policy_id=r, file="?", effect="?", annotations={})
            for r in reasons
        ]
        determining = tuple(m.label for m in metas)
        if result.allowed:
            return Decision(
                call_id=call_id, effect=Effect.ALLOW, determining=determining, engine=self.name
            )
        if not reasons and errors:
            name = missing_name(errors[0])
            reason = name if name else errors[0]
            return Decision.error(call_id, ErrorKind.MISSING_CONTEXT, reason, engine=self.name)
        if not reasons:
            return Decision(
                call_id=call_id,
                effect=Effect.DENY,
                reasons=("no permit policy applied",),
                determining=("default",),
                engine=self.name,
            )
        annotation = self.options.approval_annotation
        notes = [m.annotations.get(annotation) for m in metas]
        if all(n is not None for n in notes):
            return Decision(
                call_id=call_id,
                effect=Effect.REQUIRE_APPROVAL,
                reasons=tuple(n for n in notes if n),
                determining=determining,
                engine=self.name,
            )
        return Decision(
            call_id=call_id, effect=Effect.DENY, determining=determining, engine=self.name
        )
