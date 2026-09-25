"""``execute_tool`` and MCP ``tools/call`` spans → ``ToolCall`` (FR-4).

Tracks OpenTelemetry semantic-conventions-genai ``main`` as of 2026-09-25 (Development
stability). Attribute names may still change; ``ALIASES`` absorbs renames.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from permdiff.importers.limits import RecordRejected
from permdiff.importers.otel.spans import Span
from permdiff.models import ToolCall

FORMAT_NAME = "otel.genai"
TOOL_OPERATION = "execute_tool"
MCP_TOOLS_CALL = "tools/call"
UNKNOWN_PRINCIPAL = "unknown"
ALIASES: Mapping[str, str] = {
    "gen_ai.system": "gen_ai.provider.name",  # renamed in semconv-genai
}
_PRINCIPAL_KEYS = ("enduser.id", "user.id")
_NS_PER_S = 1_000_000_000


def normalize(attributes: Mapping[str, Any]) -> dict[str, Any]:
    """Apply aliases; the current name wins when both are present."""
    out = dict(attributes)
    for old, new in ALIASES.items():
        if old in out and new not in out:
            out[new] = out[old]
    return out


def is_tool_span(span: Span) -> bool:
    a = span.attributes
    if a.get("gen_ai.operation.name") == TOOL_OPERATION:
        return True
    if a.get("mcp.method.name") == MCP_TOOLS_CALL:
        return True
    name = span.name
    return name.startswith((f"{TOOL_OPERATION} ", f"{MCP_TOOLS_CALL} ")) or name == MCP_TOOLS_CALL


def _timestamp(span: Span) -> datetime:
    raw = span.record.get("startTimeUnixNano")
    try:
        ns = int(raw) if raw is not None else None
    except (TypeError, ValueError) as exc:
        msg = f"startTimeUnixNano missing or invalid: {raw!r}"
        raise RecordRejected(msg) from exc
    if ns is None:
        msg = "startTimeUnixNano missing"
        raise RecordRejected(msg)
    return datetime.fromtimestamp(ns / _NS_PER_S, tz=UTC)


def _lookup(span: Span, path: str) -> Any:
    """``attr.<key>`` (span), ``resource.attr.<key>``, or a bare span attribute key."""
    if path.startswith("resource.attr."):
        return span.resource.get(path.removeprefix("resource.attr."))
    if path.startswith("attr."):
        return span.attributes.get(path.removeprefix("attr."))
    return span.attributes.get(path, span.resource.get(path))


def principal_of(span: Span, principal_from: str | None) -> tuple[str, bool]:
    """``(principal id, found)``; ``--principal-from`` overrides the standard keys."""
    if principal_from:
        value = _lookup(span, principal_from)
        if value not in (None, ""):
            return str(value), True
        return UNKNOWN_PRINCIPAL, False
    for source in (span.attributes, span.resource):
        for key in _PRINCIPAL_KEYS:
            if source.get(key) not in (None, ""):
                return str(source[key]), True
    return UNKNOWN_PRINCIPAL, False


def parse_arguments(raw: Any) -> Mapping[str, Any] | None:
    """Opt-In ``gen_ai.tool.call.arguments``: JSON text or a kvlist-decoded object."""
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {"_raw": raw}
        return parsed if isinstance(parsed, Mapping) else {"_value": parsed}
    if isinstance(raw, Mapping):
        return dict(raw)
    return {"_value": raw}


def tool_name(span: Span, a: Mapping[str, Any]) -> str:
    name = a.get("gen_ai.tool.name")
    if name:
        return str(name)
    for prefix in (f"{TOOL_OPERATION} ", f"{MCP_TOOLS_CALL} "):
        if span.name.startswith(prefix) and span.name[len(prefix) :].strip():
            return span.name[len(prefix) :].strip()
    msg = "gen_ai.tool.name missing and the span name carries no tool"
    raise RecordRejected(msg)


def to_toolcall(
    span: Span, *, principal_from: str | None = None, arguments: Any = None
) -> ToolCall:
    a = normalize(span.attributes)
    principal, found = principal_of(span, principal_from)
    agent = (
        a.get("gen_ai.agent.name") or a.get("gen_ai.agent.id") or span.resource.get("service.name")
    )
    context: dict[str, Any] = {
        "otel.trace_id": span.record.get("traceId"),
        "otel.span_id": span.span_id,
    }
    for key, ctx in (
        ("gen_ai.conversation.id", "session_id"),
        ("mcp.session.id", "mcp.session_id"),
        ("gen_ai.provider.name", "gen_ai.provider"),
        ("gen_ai.agent.id", "gen_ai.agent_id"),
    ):
        if a.get(key) not in (None, ""):
            context[ctx] = a[key]
    if not found:
        context["otel.principal_missing"] = True
    args = parse_arguments(
        arguments if arguments is not None else a.get("gen_ai.tool.call.arguments")
    )
    is_mcp = a.get("mcp.method.name") == MCP_TOOLS_CALL or span.name.startswith(MCP_TOOLS_CALL)
    record: dict[str, Any] = {
        "id": str(a.get("gen_ai.tool.call.id") or span.span_id or span.locator),
        "timestamp": _timestamp(span).isoformat(),
        "principal": {"id": principal, "type": "user"},
        "agent": {"id": str(agent) if agent else "unknown"},
        "tool": {
            "name": tool_name(span, a),
            "type": a.get("gen_ai.tool.type"),
            "server": "mcp" if is_mcp else None,
        },
        "arguments": args,
        "context": {k: v for k, v in context.items() if v is not None},
        "source": {"format": FORMAT_NAME, "locator": span.locator},
    }
    return ToolCall.model_validate(record)
