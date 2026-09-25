"""Importer protocol and result types."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from permdiff.models import Frozen, ToolCall
from permdiff.models.limits import DEFAULT_MAX_RECORDS


class ImportStats(Frozen):
    """Counts that let the report footer reconcile imported versus skipped."""

    read: int
    skipped: int
    skipped_locators: tuple[str, ...]
    """``path:line: reason`` for every skipped record, in file order."""


class ImportResult(Frozen):
    calls: tuple[ToolCall, ...]
    stats: ImportStats


@runtime_checkable
class Importer(Protocol):
    """One trace format. Third parties register via the ``permdiff.importers`` entry point."""

    name: str

    def detect(self, head: bytes) -> bool:
        """Whether the first bytes of a file look like this format."""
        ...

    def read(
        self, path: Path, *, strict: bool = False, max_records: int = DEFAULT_MAX_RECORDS
    ) -> ImportResult:
        """Parse ``path``. Strict aborts on the first bad record; default skips and counts."""
        ...
