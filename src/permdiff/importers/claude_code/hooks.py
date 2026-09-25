"""Claude Code ``PreToolUse`` hook-log importer.

One hook stdin object per line, as documented at code.claude.com/docs/en/hooks (read
2026-09-25), plus a ``ts`` key added by the hook itself because the stdin carries no
timestamp. ``docs/importers.md`` shows the hook. Other hook events on the same file are
skipped silently; hooks never see a decision, so ``recorded.effect`` stays unset.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import AwareDatetime as AwareDatetimeType
from pydantic import TypeAdapter, ValidationError

from permdiff.importers.base import ImportResult
from permdiff.importers.claude_code.mapping import (
    FORMAT_HOOKS,
    build_toolcall,
    parse_object,
    principal_of,
    require_mapping,
)
from permdiff.importers.limits import RecordRejected
from permdiff.importers.lines import first_nonblank_line, read_lines
from permdiff.models import ToolCall
from permdiff.models.limits import DEFAULT_MAX_RECORDS

log = logging.getLogger(__name__)

PRE_TOOL_USE = "PreToolUse"
EVENT_KEY = "hook_event_name"
TIMESTAMP_KEY = "ts"
HOOK_COMMAND = "jq -c '. + {ts: (now | todate)}' >> FILE"
"""The documented PreToolUse hook command; the importer names it when ``ts`` is missing."""
_CONTEXT_KEYS = (
    ("session_id", "session_id"),
    ("cwd", "cwd"),
    ("permission_mode", "permission_mode"),
    ("agent_id", "claude_code.agent_id"),
    ("agent_type", "claude_code.agent_type"),
)
_aware = TypeAdapter(AwareDatetimeType)


def _timestamp(event: Mapping[str, Any]) -> datetime:
    raw = event.get(TIMESTAMP_KEY)
    if raw in (None, ""):
        msg = f"no {TIMESTAMP_KEY}: hook stdin carries no timestamp; log it with `{HOOK_COMMAND}`"
        raise RecordRejected(msg)
    try:
        return _aware.validate_python(raw)
    except ValidationError as exc:
        msg = f"{TIMESTAMP_KEY} is not an RFC 3339 timestamp with a zone: {raw!r}"
        raise RecordRejected(msg) from exc


def _context(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        target: event[source]
        for source, target in _CONTEXT_KEYS
        if event.get(source) not in (None, "")
    }


def to_toolcall(event: Mapping[str, Any], locator: str, principal_from: str | None) -> ToolCall:
    tool = event.get("tool_name")
    if not isinstance(tool, str) or not tool:
        msg = "missing required field tool_name"
        raise RecordRejected(msg)
    arguments = require_mapping(event, "tool_input")
    timestamp = _timestamp(event)
    call_id = event.get("tool_use_id")
    if not isinstance(call_id, str) or not call_id:
        principal, _ = principal_of(event, principal_from)
        call_id = ToolCall.derived_id(timestamp, principal, tool, arguments)
    return build_toolcall(
        call_id=call_id,
        timestamp=timestamp,
        tool=tool,
        arguments=arguments,
        record=event,
        principal_from=principal_from,
        context=_context(event),
        recorded_effect=None,
        fmt=FORMAT_HOOKS,
        locator=locator,
    )


class ClaudeCodeHooksImporter:
    name = FORMAT_HOOKS

    def __init__(self, principal_from: str | None = None) -> None:
        self.principal_from = principal_from

    def detect(self, head: bytes) -> bool:
        line = first_nonblank_line(head)
        if line is None:
            return False
        try:
            record = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            return False
        return isinstance(record, dict) and EVENT_KEY in record

    def read(
        self, path: Path, *, strict: bool = False, max_records: int = DEFAULT_MAX_RECORDS
    ) -> ImportResult:
        def parse(text: str, locator: str) -> ToolCall | None:
            event = parse_object(text)
            if event.get(EVENT_KEY) != PRE_TOOL_USE:
                return None
            return to_toolcall(event, locator, self.principal_from)

        result = read_lines(path, parse, strict=strict, max_records=max_records)
        missing = sum(1 for c in result.calls if c.context.get("claude_code.principal_missing"))
        if missing:
            log.warning(
                "%d of %d Claude Code hook calls carry no principal; principal is 'unknown' "
                "(use --principal-from env:USER)",
                missing,
                len(result.calls),
            )
        return result
