"""Line-level guards shared by line-oriented importers (AC-1.4, AC-2.3)."""

from __future__ import annotations

from permdiff.errors import TraceImportError
from permdiff.models.limits import MAX_LINE_BYTES


class RecordRejected(Exception):  # noqa: N818  # internal control flow, not a user-facing error
    """A single record failed; carries the reason. Callers decide skip versus abort."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def check_line_size(raw: bytes, *, limit: int = MAX_LINE_BYTES) -> None:
    """Raise ``RecordRejected`` when a line exceeds ``limit`` bytes."""
    if len(raw) > limit:
        msg = f"line is {len(raw)} bytes, over the {limit >> 20} MiB limit"
        raise RecordRejected(msg)


def decode_utf8(raw: bytes, *, locator: str) -> str:
    """Decode strictly; invalid UTF-8 is always fatal (AC-2.3)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"{locator}: not valid UTF-8 at byte {exc.start}"
        raise TraceImportError(msg) from exc
