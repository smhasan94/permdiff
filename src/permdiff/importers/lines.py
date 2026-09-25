"""Shared loop for line-oriented importers: skip-or-abort per record, cap, locators."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from permdiff.errors import TraceImportError
from permdiff.importers.base import ImportResult, ImportStats
from permdiff.importers.limits import RecordRejected, check_line_size, decode_utf8
from permdiff.models import ToolCall
from permdiff.models.limits import DEFAULT_MAX_RECORDS

log = logging.getLogger(__name__)

LineParser = Callable[[str, str], ToolCall | None]
"""``(text, locator) -> ToolCall``; ``None`` skips silently (not an error), raise RecordRejected."""

MultiLineParser = Callable[[str, str], Sequence[ToolCall]]
"""``(text, locator) -> calls``; an empty sequence skips silently, raise RecordRejected."""


def first_nonblank_line(head: bytes, limit: int = 4096) -> bytes | None:
    for line in head[:limit].splitlines():
        if line.strip():
            return line
    return None


def read_lines(
    path: Path,
    parse: LineParser,
    *,
    strict: bool = False,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> ImportResult:
    """One call (or none) per line."""

    def one(text: str, locator: str) -> Sequence[ToolCall]:
        call = parse(text, locator)
        return () if call is None else (call,)

    return read_lines_multi(path, one, strict=strict, max_records=max_records)


def read_lines_multi(
    path: Path,
    parse: MultiLineParser,
    *,
    strict: bool = False,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> ImportResult:
    """Any number of calls per line; the record cap counts calls."""
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
                    check_line_size(line)
                    parsed = parse(decode_utf8(line, locator=locator), locator)
                except RecordRejected as exc:
                    message = f"{locator}: {exc.reason}"
                    if strict:
                        raise TraceImportError(message) from exc
                    log.warning("skipping %s", message)
                    skipped.append(message)
                    continue
                calls.extend(parsed)
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
