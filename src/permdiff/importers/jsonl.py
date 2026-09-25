"""permdiff JSONL importer: one ``ToolCall`` JSON object per line (FR-2)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from permdiff.importers.base import ImportResult
from permdiff.importers.limits import RecordRejected
from permdiff.importers.lines import first_nonblank_line, read_lines
from permdiff.models import Source, ToolCall
from permdiff.models.limits import DEFAULT_MAX_RECORDS

FORMAT_NAME = "permdiff.jsonl"
_REQUIRED_KEYS = frozenset({"id", "timestamp", "principal", "agent", "tool"})


def summarize_validation_error(exc: ValidationError, limit: int = 3) -> str:
    parts = []
    for err in exc.errors(include_url=False):
        loc = ".".join(str(p) for p in err["loc"]) or "<record>"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts[:limit])


class JsonlImporter:
    name = "jsonl"

    def detect(self, head: bytes) -> bool:
        line = first_nonblank_line(head)
        if line is None:
            return False
        try:
            record = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            return False
        return isinstance(record, dict) and record.keys() >= _REQUIRED_KEYS

    def read(
        self, path: Path, *, strict: bool = False, max_records: int = DEFAULT_MAX_RECORDS
    ) -> ImportResult:
        return read_lines(path, _parse_line, strict=strict, max_records=max_records)


def _parse_line(text: str, locator: str) -> ToolCall:
    try:
        call = ToolCall.model_validate_json(text)
    except ValidationError as exc:
        raise RecordRejected(summarize_validation_error(exc)) from exc
    except RecursionError as exc:
        msg = "JSON nested too deeply"
        raise RecordRejected(msg) from exc
    if call.source is None:
        return call.model_copy(update={"source": Source(format=FORMAT_NAME, locator=locator)})
    return call
