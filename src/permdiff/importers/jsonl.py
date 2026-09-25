"""permdiff JSONL importer: one ``ToolCall`` JSON object per line (FR-2)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from permdiff.errors import TraceImportError
from permdiff.importers.base import ImportResult, ImportStats
from permdiff.importers.limits import RecordRejected, check_line_size, decode_utf8
from permdiff.models import Source, ToolCall
from permdiff.models.limits import DEFAULT_MAX_RECORDS

log = logging.getLogger(__name__)

FORMAT_NAME = "permdiff.jsonl"
_REQUIRED_KEYS = frozenset({"id", "timestamp", "principal", "agent", "tool"})
_FIRST_LINE_SNIFF_BYTES = 4096


def _first_nonblank_line(head: bytes) -> bytes | None:
    for line in head.splitlines():
        if line.strip():
            return line
    return None


class JsonlImporter:
    name = "jsonl"

    def detect(self, head: bytes) -> bool:
        line = _first_nonblank_line(head[:_FIRST_LINE_SNIFF_BYTES])
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
        calls: list[ToolCall] = []
        skipped: list[str] = []
        try:
            with path.open("rb") as fh:
                for lineno, raw in enumerate(fh, start=1):
                    line = raw.rstrip(b"\r\n")
                    if not line.strip():
                        continue
                    locator = f"{path}:{lineno}"
                    try:
                        calls.append(_parse_line(line, locator))
                    except RecordRejected as exc:
                        message = f"{locator}: {exc.reason}"
                        if strict:
                            raise TraceImportError(message) from exc
                        log.warning("skipping %s", message)
                        skipped.append(message)
                        continue
                    if len(calls) > max_records:
                        msg = (
                            f"{locator}: corpus exceeds max_records={max_records}; "
                            "raise the cap or split the input"
                        )
                        raise TraceImportError(msg)
        except OSError as exc:
            msg = f"cannot read {path}: {exc.strerror or exc}"
            raise TraceImportError(msg) from exc
        stats = ImportStats(read=len(calls), skipped=len(skipped), skipped_locators=tuple(skipped))
        return ImportResult(calls=tuple(calls), stats=stats)


def _parse_line(line: bytes, locator: str) -> ToolCall:
    check_line_size(line)
    text = decode_utf8(line, locator=locator)
    try:
        call = ToolCall.model_validate_json(text)
    except ValidationError as exc:
        raise RecordRejected(_summarize(exc)) from exc
    if call.source is None:
        return call.model_copy(update={"source": Source(format=FORMAT_NAME, locator=locator)})
    return call


def _summarize(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors(include_url=False):
        loc = ".".join(str(p) for p in err["loc"]) or "<record>"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts[:3])
