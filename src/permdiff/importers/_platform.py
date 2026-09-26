"""Shared pieces for the Langfuse and LangSmith importers (E13)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from permdiff.errors import TraceImportError
from permdiff.importers.base import ImportResult, ImportStats
from permdiff.importers.input_map import resolve_source
from permdiff.importers.jsonl import summarize_validation_error
from permdiff.importers.limits import RecordRejected
from permdiff.importers.rows import Row, iter_rows, parse_json_field
from permdiff.models import ToolCall
from permdiff.models.limits import DEFAULT_MAX_RECORDS

UNKNOWN_PRINCIPAL = "unknown"
RowMapper = Callable[[Row, str], ToolCall | None]
"""``(row, locator) -> ToolCall`` or ``None`` to skip silently; raise ``RecordRejected``."""


def first(row: Row, *keys: str) -> Any:
    """The first non-empty value among alternative spellings of a column."""
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def require(row: Row, label: str, *keys: str) -> Any:
    value = first(row, *keys)
    if value is None:
        msg = f"missing required field {label}"
        raise RecordRejected(msg)
    return value


def utc_timestamp(value: Any, label: str = "timestamp") -> str:
    """ISO text; a naive timestamp is taken as UTC (LangSmith writes them without a zone)."""
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        return moment.isoformat()
    if not isinstance(value, str) or not value:
        msg = f"missing required field {label}"
        raise RecordRejected(msg)
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        msg = f"{label} is not an ISO 8601 timestamp: {value!r}"
        raise RecordRejected(msg) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.isoformat()


def arguments_of(value: Any, label: str) -> Mapping[str, Any] | None:
    """A JSON object (parsed from text when needed); other text is kept under ``_raw``."""
    parsed = parse_json_field(value)
    if parsed is None:
        return None
    if isinstance(parsed, Mapping):
        return dict(parsed)
    if isinstance(parsed, str):
        return {"_raw": parsed}
    msg = f"{label} must be a JSON object, got {type(parsed).__name__}"
    raise RecordRejected(msg)


def principal_of(
    row: Row, principal_from: str | None, default_paths: tuple[str, ...]
) -> tuple[str, bool]:
    """``(principal id, found)`` from ``--principal-from`` (dotted path) or the defaults."""
    paths = (principal_from,) if principal_from else default_paths
    for path in paths:
        value = resolve_source(path, input=row, event=row)
        if value not in (None, ""):
            return str(value), True
    return UNKNOWN_PRINCIPAL, False


def validate(payload: Mapping[str, Any]) -> ToolCall:
    try:
        return ToolCall.model_validate(payload)
    except ValidationError as exc:
        raise RecordRejected(summarize_validation_error(exc)) from exc


def read_rows(
    path: Path,
    mapper: RowMapper,
    *,
    strict: bool,
    max_records: int = DEFAULT_MAX_RECORDS,
    missing_key: str,
    log: logging.Logger,
    hint: str,
) -> ImportResult:
    """Skip-or-abort loop over ``iter_rows`` with the shared principal-missing warning."""
    calls: list[ToolCall] = []
    skipped: list[str] = []
    for row, locator in iter_rows(path):
        try:
            if isinstance(row, RecordRejected):
                raise row
            call = mapper(row, locator)
        except RecordRejected as exc:
            message = f"{locator}: {exc.reason}"
            if strict:
                raise TraceImportError(message) from exc
            log.warning("skipping %s", message)
            skipped.append(message)
            continue
        if call is None:
            continue
        calls.append(call)
        if len(calls) > max_records:
            msg = f"{locator}: corpus exceeds max_records={max_records}"
            raise TraceImportError(msg)
    missing = sum(1 for c in calls if c.context.get(missing_key))
    if missing:
        log.warning(
            "%d of %d calls carry no principal; principal is 'unknown' (%s)",
            missing,
            len(calls),
            hint,
        )
    stats = ImportStats(read=len(calls), skipped=len(skipped), skipped_locators=tuple(skipped))
    return ImportResult(calls=tuple(calls), stats=stats)


def sniff_row(head: bytes) -> Row | None:
    """The first row of a JSONL head or of a JSON array/page head, for ``detect``."""
    import json  # noqa: PLC0415
    import re  # noqa: PLC0415

    stripped = head.lstrip()
    if not stripped or stripped.startswith(b"\x1f\x8b") or stripped.startswith(b"PAR1"):
        return None
    page = re.match(rb'\{\s*"data"\s*:\s*\[', stripped)
    if page:
        stripped = stripped[page.end() :].lstrip()
    elif stripped.startswith(b"["):
        stripped = stripped[1:].lstrip()
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(stripped.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    return obj if isinstance(obj, Mapping) else None
