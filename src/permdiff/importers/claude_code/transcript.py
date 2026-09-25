"""Claude Code session transcript importer (``~/.claude/projects/<slug>/<session>.jsonl``).

The format is undocumented. Facts here come from transcripts written by Claude Code 2.1.282
(read 2026-09-25, see ``tests/fixtures/claude_code/README.md``): ``assistant`` lines carry
``tool_use`` blocks, later ``user`` lines carry the matching ``tool_result`` and, on a
denial, ``toolDenialKind``. Unknown keys and line types are ignored so additive changes
keep working.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from permdiff.errors import TraceImportError
from permdiff.importers.base import ImportResult
from permdiff.importers.claude_code.mapping import (
    FORMAT_TRANSCRIPT,
    build_toolcall,
    parse_object,
)
from permdiff.importers.limits import RecordRejected
from permdiff.importers.lines import first_nonblank_line, read_lines_multi
from permdiff.models import Effect, ToolCall
from permdiff.models.limits import DEFAULT_MAX_RECORDS

log = logging.getLogger(__name__)

TOOL_USE = "tool_use"
TOOL_RESULT = "tool_result"
PERMISSION_MODE_LINE = "permission-mode"
_RESULT_MARKER = b'"tool_result"'
_SESSION_KEYS = ("sessionId", "session_id")
_HOOK_MARKER = "hook_event_name"

ResultIndex = Mapping[str, str | None]
"""``tool_use_id`` → ``toolDenialKind`` (``None`` when the call ran)."""


def _blocks(record: Mapping[str, Any], kind: str) -> list[Mapping[str, Any]]:
    message = record.get("message")
    content = message.get("content") if isinstance(message, Mapping) else None
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, Mapping) and b.get("type") == kind]


def index_results(path: Path) -> ResultIndex:
    """First pass: which calls got a result, and which were denied. Bad lines wait for pass 2."""
    index: dict[str, str | None] = {}
    try:
        with path.open("rb") as fh:
            for raw in fh:
                if _RESULT_MARKER not in raw:
                    continue
                try:
                    record = json.loads(raw)
                except (ValueError, RecursionError):
                    continue
                if not isinstance(record, Mapping):
                    continue
                denial = record.get("toolDenialKind")
                for block in _blocks(record, TOOL_RESULT):
                    call_id = block.get("tool_use_id")
                    if isinstance(call_id, str):
                        index[call_id] = str(denial) if denial else None
    except OSError as exc:
        msg = f"cannot read {path}: {exc.strerror or exc}"
        raise TraceImportError(msg) from exc
    return index


def _context(record: Mapping[str, Any], permission_mode: str | None) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for source_key, target_key in (
        ("cwd", "cwd"),
        ("gitBranch", "git_branch"),
        ("version", "claude_code.version"),
        ("agentId", "claude_code.agent_id"),
    ):
        if record.get(source_key) not in (None, ""):
            context[target_key] = record[source_key]
    for key in _SESSION_KEYS:
        if record.get(key) not in (None, ""):
            context["session_id"] = record[key]
            break
    if permission_mode is not None:
        context["permission_mode"] = permission_mode
    context["claude_code.sidechain"] = bool(record.get("isSidechain", False))
    return context


def _recorded(call_id: str, results: ResultIndex) -> tuple[Effect | None, str | None]:
    if call_id not in results:
        return None, None
    denial = results[call_id]
    return (Effect.DENY, denial) if denial else (Effect.ALLOW, None)


class _TranscriptParser:
    """Line parser with the little state a transcript needs: the last permission mode."""

    def __init__(self, results: ResultIndex, principal_from: str | None) -> None:
        self._results = results
        self._principal_from = principal_from
        self._permission_mode: str | None = None

    def __call__(self, text: str, locator: str) -> Sequence[ToolCall]:
        record = parse_object(text)
        if record.get("type") == PERMISSION_MODE_LINE:
            mode = record.get("permissionMode")
            self._permission_mode = str(mode) if mode else self._permission_mode
            return ()
        blocks = _blocks(record, TOOL_USE)
        if not blocks:
            return ()
        timestamp = record.get("timestamp")
        if not timestamp:
            msg = "tool_use line has no timestamp"
            raise RecordRejected(msg)
        base_context = _context(record, self._permission_mode)
        wire = record.get("wireToolInputs")
        wire_inputs: Mapping[str, Any] = wire if isinstance(wire, Mapping) else {}
        return tuple(
            self._call(block, record, timestamp, base_context, wire_inputs, locator)
            for block in blocks
        )

    def _call(
        self,
        block: Mapping[str, Any],
        record: Mapping[str, Any],
        timestamp: Any,
        base_context: Mapping[str, Any],
        wire_inputs: Mapping[str, Any],
        locator: str,
    ) -> ToolCall:
        call_id = block.get("id")
        if not isinstance(call_id, str) or not call_id:
            msg = "tool_use block has no id"
            raise RecordRejected(msg)
        tool = block.get("name")
        if not isinstance(tool, str) or not tool:
            msg = f"tool_use block {call_id} has no name"
            raise RecordRejected(msg)
        model_input = block.get("input")
        wire_input = wire_inputs.get(call_id)
        arguments = wire_input if isinstance(wire_input, Mapping) else model_input
        if arguments is not None and not isinstance(arguments, Mapping):
            msg = f"tool_use block {call_id} input must be an object"
            raise RecordRejected(msg)
        effect, denial = _recorded(call_id, self._results)
        context = dict(base_context)
        if denial:
            context["claude_code.denial_kind"] = denial
        if isinstance(wire_input, Mapping) and wire_input != model_input:
            context["claude_code.model_input_differs"] = True
        version = record.get("version")
        return build_toolcall(
            call_id=call_id,
            timestamp=timestamp,
            tool=tool,
            arguments=arguments,
            record=record,
            principal_from=self._principal_from,
            context=context,
            recorded_effect=effect,
            fmt=FORMAT_TRANSCRIPT,
            locator=locator,
            agent_version=str(version) if version else None,
        )


class ClaudeCodeImporter:
    name = FORMAT_TRANSCRIPT

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
        if not isinstance(record, dict) or "type" not in record or _HOOK_MARKER in record:
            return False
        return any(key in record for key in _SESSION_KEYS)

    def read(
        self, path: Path, *, strict: bool = False, max_records: int = DEFAULT_MAX_RECORDS
    ) -> ImportResult:
        parser = _TranscriptParser(index_results(path), self.principal_from)
        result = read_lines_multi(path, parser, strict=strict, max_records=max_records)
        missing = sum(1 for c in result.calls if c.context.get("claude_code.principal_missing"))
        if missing:
            log.warning(
                "%d of %d Claude Code calls carry no principal; principal is 'unknown' "
                "(use --principal-from env:USER or a top-level transcript key)",
                missing,
                len(result.calls),
            )
        return result
