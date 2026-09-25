"""Shared mapping for the Claude Code importers (FR-L3): transcripts and hook logs."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from permdiff.importers.jsonl import summarize_validation_error
from permdiff.importers.limits import RecordRejected
from permdiff.models import Effect, ToolCall

FORMAT_TRANSCRIPT = "claude-code"
FORMAT_HOOKS = "claude-code-hooks"
AGENT_ID = "claude-code"
UNKNOWN_PRINCIPAL = "unknown"
"""Same literal as the OTel importer: neither source records who ran the session."""
MCP_PREFIX = "mcp__"
ENV_PREFIX = "env:"
SHELL_TOOLS = frozenset({"Bash"})
RESOURCE_KEYS: tuple[tuple[str, str], ...] = (
    ("file_path", "file"),
    ("notebook_path", "file"),
    ("path", "file"),
    ("url", "url"),
)
"""``tool_input`` keys that name a resource, first match wins (built-in tool inputs)."""


def split_tool(name: str) -> tuple[str | None, str | None]:
    """``mcp__<server>__<tool>`` → ``(server, "mcp")``; built-in tools → ``(None, None)``."""
    if not name.startswith(MCP_PREFIX):
        return None, None
    server, sep, tool = name[len(MCP_PREFIX) :].partition("__")
    if not server or not sep or not tool:
        return None, None
    return server, "mcp"


def resource_of(tool: str, arguments: Mapping[str, Any] | None) -> dict[str, str]:
    """Resource type and id inferred from the tool and its input; empty when unknown."""
    if tool in SHELL_TOOLS:
        return {"type": "shell"}
    if arguments is None:
        return {}
    for key, kind in RESOURCE_KEYS:
        value = arguments.get(key)
        if isinstance(value, str) and value:
            return {"type": kind, "id": value}
    return {}


def principal_of(record: Mapping[str, Any], principal_from: str | None) -> tuple[str, bool]:
    """``(principal id, found)``: ``env:<VAR>`` reads the environment, else a top-level key."""
    if not principal_from:
        return UNKNOWN_PRINCIPAL, False
    if principal_from.startswith(ENV_PREFIX):
        value: Any = os.environ.get(principal_from[len(ENV_PREFIX) :])
    else:
        value = record.get(principal_from)
    if value in (None, ""):
        return UNKNOWN_PRINCIPAL, False
    return str(value), True


def build_toolcall(
    *,
    call_id: str,
    timestamp: Any,
    tool: str,
    arguments: Mapping[str, Any] | None,
    record: Mapping[str, Any],
    principal_from: str | None,
    context: Mapping[str, Any],
    recorded_effect: Effect | None,
    fmt: str,
    locator: str,
    agent_version: str | None = None,
) -> ToolCall:
    principal, found = principal_of(record, principal_from)
    server, tool_type = split_tool(tool)
    full_context = dict(context)
    if not found:
        full_context["claude_code.principal_missing"] = True
    payload: dict[str, Any] = {
        "id": call_id,
        "timestamp": timestamp,
        "principal": {"id": principal, "type": "user"},
        "agent": {"id": AGENT_ID, "version": agent_version},
        "tool": {"name": tool, "server": server, "type": tool_type},
        "arguments": dict(arguments) if arguments is not None else None,
        "resource": resource_of(tool, arguments),
        "context": full_context,
        "recorded": {"effect": recorded_effect.value if recorded_effect else None},
        "source": {"format": fmt, "locator": locator},
    }
    try:
        return ToolCall.model_validate(payload)
    except ValidationError as exc:
        raise RecordRejected(summarize_validation_error(exc)) from exc


def require_mapping(obj: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = obj.get(key)
    if not isinstance(value, Mapping):
        msg = f"field {key} must be an object"
        raise RecordRejected(msg)
    return value


def parse_object(text: str) -> Mapping[str, Any]:
    """One JSON object per line; anything else is a rejected record."""
    try:
        event = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"invalid JSON: {exc.msg} at column {exc.colno}"
        raise RecordRejected(msg) from exc
    except RecursionError as exc:
        msg = "JSON nested too deeply"
        raise RecordRejected(msg) from exc
    if not isinstance(event, Mapping):
        msg = "expected a JSON object"
        raise RecordRejected(msg)
    return event
