"""OpenTelemetry GenAI importer: ``execute_tool`` and MCP ``tools/call`` spans (FR-4)."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError

from permdiff.errors import TraceImportError
from permdiff.importers.base import ImportResult, ImportStats
from permdiff.importers.jsonl import summarize_validation_error
from permdiff.importers.limits import RecordRejected
from permdiff.importers.lines import first_nonblank_line
from permdiff.importers.otel.fallback import find_arguments
from permdiff.importers.otel.mapping import FORMAT_NAME, is_tool_span, to_toolcall
from permdiff.importers.otel.spans import Span, iter_spans
from permdiff.models import ToolCall
from permdiff.models.limits import DEFAULT_MAX_RECORDS

log = logging.getLogger(__name__)

__all__ = ["FORMAT_NAME", "OtelImporter", "Span"]


class OtelImporter:
    name = "otel"

    def __init__(self, principal_from: str | None = None) -> None:
        self.principal_from = principal_from

    def detect(self, head: bytes) -> bool:
        stripped = head.lstrip()
        if not stripped.startswith(b"{"):
            return False
        line = first_nonblank_line(head)
        return b'"resourceSpans"' in head[:8192] or (line is not None and b"resourceSpans" in line)

    def read(
        self, path: Path, *, strict: bool = False, max_records: int = DEFAULT_MAX_RECORDS
    ) -> ImportResult:
        calls: list[ToolCall] = []
        skipped: list[str] = []
        missing_principal = 0
        spans = list(iter_spans(path))
        by_id = {s.span_id: s for s in spans if s.span_id}
        for span in spans:
            if not is_tool_span(span):
                continue
            try:
                arguments = None
                if span.attributes.get("gen_ai.tool.call.arguments") is None:
                    arguments = find_arguments(
                        span,
                        by_id,
                        call_id=_text(span.attributes.get("gen_ai.tool.call.id")),
                        tool=_text(span.attributes.get("gen_ai.tool.name")) or "",
                    )
                call = to_toolcall(span, principal_from=self.principal_from, arguments=arguments)
            except (RecordRejected, ValidationError) as exc:
                reason = (
                    summarize_validation_error(exc)
                    if isinstance(exc, ValidationError)
                    else exc.reason
                )
                message = f"{span.locator}: {reason}"
                if strict:
                    raise TraceImportError(message) from exc
                log.warning("skipping %s", message)
                skipped.append(message)
                continue
            if call.context.get("otel.principal_missing"):
                missing_principal += 1
            calls.append(call)
            if len(calls) > max_records:
                msg = f"{span.locator}: corpus exceeds max_records={max_records}"
                raise TraceImportError(msg)
        if missing_principal:
            log.warning(
                "%d of %d tool spans carry no enduser.id/user.id; principal is 'unknown' "
                "(use --principal-from)",
                missing_principal,
                len(calls),
            )
        stats = ImportStats(read=len(calls), skipped=len(skipped), skipped_locators=tuple(skipped))
        return ImportResult(calls=tuple(calls), stats=stats)


def _text(value: object) -> str | None:
    return None if value in (None, "") else str(value)
