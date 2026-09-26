"""LangSmith importer (FR-L2): ``tool`` runs from SDK dumps or bulk exports.

Verified 2026-09-26 against the LangSmith docs (`run-data-format`, `data-export`);
fixtures are hand-built, see ``tests/fixtures/langsmith/README.md``. Run ``start_time``
values carry no zone and are taken as UTC; ``inputs``/``outputs``/``extra`` may be JSON
text in Parquet exports.
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

FORMAT_NAME = "langsmith"
TOOL_RUN_TYPE = "tool"
DEFAULT_AGENT = "langsmith"
PRINCIPAL_PATHS = ("extra.metadata.user_id", "extra.metadata.user", "extra.metadata.userId")
PRINCIPAL_HINT = "use --principal-from with a dotted path such as extra.metadata.user_id"
MISSING_KEY = "langsmith.principal_missing"
_CONTEXT = (
    ("trace_id", "trace_id"),
    ("parent_run_id", "langsmith.parent_run_id"),
    ("dotted_order", "langsmith.dotted_order"),
    ("tags", "langsmith.tags"),
    ("status", "langsmith.status"),
    ("error", "langsmith.error"),
)


def _decoded(row: Row) -> dict[str, Any]:
    """The row with JSON-text columns decoded (bulk exports store them as text)."""
    decoded = dict(row)
    for key in ("inputs", "outputs", "extra"):
        if key in decoded:
            decoded[key] = parse_json_field(decoded[key])
    return decoded


def to_toolcall(raw: Row, locator: str, *, principal_from: str | None) -> ToolCall:
    row = _decoded(raw)
    principal, found = principal_of(row, principal_from, PRINCIPAL_PATHS)
    context: dict[str, Any] = {}
    for key, target in _CONTEXT:
        value = row.get(key)
        if value not in (None, "", []):
            context[target] = value
    extra = row.get("extra")
    metadata = extra.get("metadata") if isinstance(extra, dict) else None
    if metadata not in (None, {}):
        context["langsmith.metadata"] = metadata
    outputs = row.get("outputs")
    if outputs not in (None, {}):
        context["langsmith.outputs"] = outputs
    if not found:
        context[MISSING_KEY] = True
    payload = {
        "id": require(row, "id", "id"),
        "timestamp": utc_timestamp(first(row, "start_time"), "start_time"),
        "principal": {"id": principal, "type": "user"},
        "agent": {"id": first(row, "session_id") or DEFAULT_AGENT},
        "tool": {"name": require(row, "name", "name")},
        "arguments": arguments_of(row.get("inputs"), "inputs"),
        "context": context,
        "source": {"format": FORMAT_NAME, "locator": locator},
    }
    return validate(payload)


class LangsmithImporter:
    name = FORMAT_NAME

    def __init__(self, principal_from: str | None = None) -> None:
        self.principal_from = principal_from

    def detect(self, head: bytes) -> bool:
        row = sniff_row(head)
        return row is not None and "run_type" in row

    def read(
        self, path: Path, *, strict: bool = False, max_records: int = DEFAULT_MAX_RECORDS
    ) -> ImportResult:
        def mapper(row: Row, locator: str) -> ToolCall | None:
            if row.get("run_type") != TOOL_RUN_TYPE:
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
