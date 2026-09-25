"""Custody ``custody.trace.v1`` importer (FR-3).

Derived from the Custody planning spec (``PLAN.md`` §5, commit bb81683, read 2026-09-25),
not from real Custody output: Custody has emitted no traces yet. Extra fields are ignored so
additive schema changes keep working; a different ``schema`` value is rejected.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from permdiff.importers.base import ImportResult
from permdiff.importers.jsonl import summarize_validation_error
from permdiff.importers.limits import RecordRejected
from permdiff.importers.lines import first_nonblank_line, read_lines
from permdiff.models import Effect, ToolCall
from permdiff.models.limits import DEFAULT_MAX_RECORDS

CUSTODY_SCHEMA = "custody.trace.v1"
VERDICT_MAP: Mapping[str, Effect] = {
    "allow": Effect.ALLOW,
    "block": Effect.DENY,
    "warn": Effect.ALLOW,  # the runtime let it through; the original verdict is kept in context
    "observe": Effect.ALLOW,
}
ACTION_TYPES = frozenset(
    {
        "exec",
        "file_read",
        "file_write",
        "file_delete",
        "network",
        "tool_call",
        "mcp_call",
        "llm_call",
    }
)
DIGEST_ONLY_NOTE = "digest-only trace: arguments not exported"


def _require(obj: Mapping[str, Any], key: str, where: str) -> Any:
    value = obj.get(key)
    if value in (None, ""):
        msg = f"missing required field {where}.{key}" if where else f"missing required field {key}"
        raise RecordRejected(msg)
    return value


def _mapping(obj: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = obj.get(key)
    if not isinstance(value, Mapping):
        msg = f"field {key} must be an object"
        raise RecordRejected(msg)
    return value


def _context(
    event: Mapping[str, Any], action: Mapping[str, Any], decision: Mapping[str, Any]
) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for key in ("session_id", "workspace", "source"):
        if event.get(key) is not None:
            context[key] = event[key]
    for key in ("cwd", "repo", "branch"):
        if action.get(key) is not None:
            context[key] = action[key]
    if action.get("input_digest") is not None:
        context["custody.input_digest"] = action["input_digest"]
    context["custody.digest_only"] = "input_redacted" not in action
    if decision.get("rule_ids"):
        context["custody.rule_ids"] = list(decision["rule_ids"])
    verdict = decision.get("verdict")
    if verdict in ("warn", "observe"):
        context["custody.verdict"] = verdict
    return context


def to_toolcall(event: Mapping[str, Any], locator: str) -> ToolCall:
    schema = event.get("schema")
    if schema != CUSTODY_SCHEMA:
        msg = f"unknown schema {schema!r}; this importer reads {CUSTODY_SCHEMA}"
        raise RecordRejected(msg)
    actor = _mapping(event, "actor")
    action = _mapping(event, "action")
    raw_decision = event.get("decision")
    decision: Mapping[str, Any] = raw_decision if isinstance(raw_decision, Mapping) else {}
    action_type = action.get("type")
    if action_type not in ACTION_TYPES:
        msg = f"unknown action.type {action_type!r}"
        raise RecordRejected(msg)
    verdict = decision.get("verdict")
    if verdict is not None and verdict not in VERDICT_MAP:
        msg = f"unknown decision.verdict {verdict!r}"
        raise RecordRejected(msg)
    arguments = action.get("input_redacted")
    if arguments is not None and not isinstance(arguments, Mapping):
        msg = "action.input_redacted must be an object"
        raise RecordRejected(msg)
    principal_attrs = {k: actor[k] for k in ("host",) if actor.get(k) is not None}
    record: dict[str, Any] = {
        "id": _require(event, "id", ""),
        "timestamp": _require(event, "ts", ""),
        "principal": {
            "id": _require(actor, "user", "actor"),
            "type": "user",
            "attrs": principal_attrs,
        },
        "agent": {"id": _require(actor, "agent", "actor")},
        "tool": {
            "name": _require(action, "name", "action"),
            "type": action_type,
            "server": "mcp" if action_type == "mcp_call" else None,
        },
        "arguments": dict(arguments) if arguments is not None else None,
        "resource": {"type": action_type, "id": action.get("repo")},
        "context": _context(event, action, decision),
        "recorded": {
            "effect": VERDICT_MAP[verdict].value if verdict else None,
            "policy_hash": decision.get("policy_hash"),
        },
        "source": {"format": CUSTODY_SCHEMA, "locator": locator},
    }
    try:
        return ToolCall.model_validate(record)
    except ValidationError as exc:
        raise RecordRejected(summarize_validation_error(exc)) from exc


class CustodyImporter:
    name = "custody"

    def detect(self, head: bytes) -> bool:
        line = first_nonblank_line(head)
        if line is None:
            return False
        try:
            record = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            return False
        return isinstance(record, dict) and str(record.get("schema", "")).startswith(
            "custody.trace."
        )

    def read(
        self, path: Path, *, strict: bool = False, max_records: int = DEFAULT_MAX_RECORDS
    ) -> ImportResult:
        return read_lines(path, _parse_line, strict=strict, max_records=max_records)


def _parse_line(text: str, locator: str) -> ToolCall:
    try:
        event = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"invalid JSON: {exc.msg} at column {exc.colno}"
        raise RecordRejected(msg) from exc
    if not isinstance(event, Mapping):
        msg = "expected a JSON object"
        raise RecordRejected(msg)
    return to_toolcall(event, locator)
