"""Requests from templates (AC-11.2) and Cedar diagnostics back to decisions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC
from typing import Any

from permdiff.models import ToolCall

TEMPLATE_FIELDS: Mapping[str, str] = {
    "principal.id": "principal.id",
    "principal.type": "principal.type",
    "agent.id": "agent.id",
    "tool.name": "tool.name",
    "tool.server": "tool.server",
    "resource.type": "resource.type",
    "resource.id": "resource.id",
}
_PLACEHOLDER = re.compile(r"\{([a-z_.]+)\}")


class MissingTemplateValue(Exception):  # noqa: N818  # carries the path name for the report
    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path


def _lookup(call: ToolCall, path: str) -> Any:
    node: Any = call
    for part in path.split("."):
        node = getattr(node, part, None)
        if node is None:
            return None
    return node


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def check_template(template: str) -> str:
    """Reject unknown ``{field}`` placeholders up front (at engine construction)."""
    unknown = [
        m.group(1) for m in _PLACEHOLDER.finditer(template) if m.group(1) not in TEMPLATE_FIELDS
    ]
    if unknown:
        msg = (
            f"template {template!r} uses unknown field(s) {', '.join(unknown)}; "
            f"choose from {', '.join(TEMPLATE_FIELDS)}"
        )
        raise ValueError(msg)
    return template


def render(template: str, call: ToolCall) -> str:
    """``User::"{principal.id}"`` → ``User::"alice"``.

    A placeholder whose value the trace lacks raises ``MissingTemplateValue``.
    """

    def sub(match: re.Match[str]) -> str:
        path = match.group(1)
        if path not in TEMPLATE_FIELDS:
            msg = f"unknown template field {{{path}}}; choose from {', '.join(TEMPLATE_FIELDS)}"
            raise ValueError(msg)
        value = _lookup(call, path)
        if value in (None, ""):
            raise MissingTemplateValue(path)
        return _escape(str(value))

    return _PLACEHOLDER.sub(sub, template)


def now_value(call: ToolCall) -> dict[str, Any]:
    """The trace timestamp as a Cedar ``datetime`` extension value (the replay clock)."""
    stamp = call.timestamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return {"__extn": {"fn": "datetime", "arg": stamp}}


CALL_KEY = "call"
"""``context.call`` carries the canonical principal, agent, tool, and resource records."""


def call_record(call: ToolCall) -> dict[str, Any]:
    return {
        "principal": call.principal.model_dump(mode="json"),
        "agent": call.agent.model_dump(mode="json"),
        "tool": call.tool.model_dump(mode="json"),
        "resource": call.resource.model_dump(mode="json"),
    }


def without_nulls(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: without_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list | tuple):
        return [without_nulls(v) for v in value if v is not None]
    return value


def build_request(
    call: ToolCall, *, principal: str, action: str, resource: str, now_key: str
) -> dict[str, Any]:
    """Context = arguments + trace context + ``call`` record + ``now`` (AC-11.2).

    Cedar has no null, so null values are dropped at every depth; a policy that needs
    one sees a missing attribute, which permdiff reports as can't-evaluate.
    """
    context: dict[str, Any] = {}
    context.update(call.arguments or {})
    context.update(call.context)
    context[CALL_KEY] = call_record(call)
    context[now_key] = now_value(call)
    context = without_nulls(context)
    return {
        "principal": render(principal, call),
        "action": render(action, call),
        "resource": render(resource, call),
        "context": context,
    }


_MISSING_ATTR = re.compile(r"does not have the attribute `([^`]+)`")
_MISSING_ENTITY = re.compile(r"entity `([^`]+)` does not exist|`([^`]+)` does not exist")
_MISSING_CONTEXT = re.compile(
    r"`context` does not have the attribute `([^`]+)`|context.*?attribute `([^`]+)`"
)


def missing_name(error: str) -> str | None:
    """Best-effort: the attribute or entity a Cedar evaluation error complains about."""
    for pattern in (_MISSING_CONTEXT, _MISSING_ATTR, _MISSING_ENTITY):
        if m := pattern.search(error):
            return next(g for g in m.groups() if g)
    return None
