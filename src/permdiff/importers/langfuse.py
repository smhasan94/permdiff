"""Langfuse importer (FR-L1): ``tool`` observations from blob-storage exports or API pages.

Verified 2026-09-26 against the Langfuse docs (`export-to-blob-storage` field groups,
`observations-api` v2 response, `observation-types`); fixtures are hand-built, see
``tests/fixtures/langfuse/README.md``. Both snake_case (export) and camelCase (API) keys
are accepted; ``input``/``output`` may be JSON text.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from permdiff.importers._platform import (
    arguments_of,
    first,
    principal_of,
    read_rows,
    require,
    sniff_row,
    utc_timestamp,
    validate,
)
from permdiff.importers.base import ImportResult
from permdiff.importers.rows import Row, parse_json_field
from permdiff.models import ToolCall
from permdiff.models.limits import DEFAULT_MAX_RECORDS

log = logging.getLogger(__name__)

FORMAT_NAME = "langfuse"
TOOL_TYPE = "tool"
DEFAULT_AGENT = "langfuse"
PRINCIPAL_PATHS = ("user_id", "userId")
PRINCIPAL_HINT = "use --principal-from with a dotted path such as metadata.user"
MISSING_KEY = "langfuse.principal_missing"
_CONTEXT = (
    (("trace_id", "traceId"), "trace_id"),
    (("session_id", "sessionId"), "session_id"),
    (("parent_observation_id", "parentObservationId"), "langfuse.parent_observation_id"),
    (("environment",), "langfuse.environment"),
    (("level",), "langfuse.level"),
    (("project_id", "projectId"), "langfuse.project_id"),
    (("tags",), "langfuse.tags"),
)


def is_tool(row: Row) -> bool:
    kind = row.get("type")
    return isinstance(kind, str) and kind.lower() == TOOL_TYPE


def to_toolcall(row: Row, locator: str, *, principal_from: str | None) -> ToolCall:
    principal, found = principal_of(row, principal_from, PRINCIPAL_PATHS)
    context: dict[str, Any] = {}
    for keys, target in _CONTEXT:
        value = first(row, *keys)
        if value is not None:
            context[target] = value
    metadata = parse_json_field(row.get("metadata"))
    if metadata not in (None, {}):
        context["langfuse.metadata"] = metadata
    output = parse_json_field(row.get("output"))
    if output is not None:
        context["langfuse.output"] = output
    if not found:
        context[MISSING_KEY] = True
    payload = {
        "id": require(row, "id", "id"),
        "timestamp": utc_timestamp(first(row, "start_time", "startTime"), "start_time"),
        "principal": {"id": principal, "type": "user"},
        "agent": {
            "id": first(row, "trace_name", "traceName") or DEFAULT_AGENT,
            "version": first(row, "version", "release"),
        },
        "tool": {"name": require(row, "name", "name")},
        "arguments": arguments_of(row.get("input"), "input"),
        "context": context,
        "source": {"format": FORMAT_NAME, "locator": locator},
    }
    return validate(payload)


class LangfuseImporter:
    name = FORMAT_NAME

    def __init__(self, principal_from: str | None = None) -> None:
        self.principal_from = principal_from

    def detect(self, head: bytes) -> bool:
        row = sniff_row(head)
        if row is None or "run_type" in row:
            return False
        return "type" in row and ("trace_id" in row or "traceId" in row)

    def read(
        self, path: Path, *, strict: bool = False, max_records: int = DEFAULT_MAX_RECORDS
    ) -> ImportResult:
        def mapper(row: Row, locator: str) -> ToolCall | None:
            if not is_tool(row):
                return None
            return to_toolcall(row, locator, principal_from=self.principal_from)

        return read_rows(
            path,
            mapper,
            strict=strict,
            max_records=max_records,
            missing_key=MISSING_KEY,
            log=log,
            hint=PRINCIPAL_HINT,
        )
