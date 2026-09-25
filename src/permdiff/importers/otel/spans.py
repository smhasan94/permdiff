"""Walk OTLP/JSON trace documents (``resourceSpans → scopeSpans → spans``)."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from permdiff.errors import TraceImportError
from permdiff.importers.limits import decode_utf8
from permdiff.importers.otel.anyvalue import attrs
from permdiff.models import Frozen


class Span(Frozen):
    record: Mapping[str, Any]
    attributes: Mapping[str, Any]
    resource: Mapping[str, Any]
    locator: str

    @property
    def span_id(self) -> str:
        return str(self.record.get("spanId", ""))

    @property
    def parent_id(self) -> str:
        return str(self.record.get("parentSpanId", ""))

    @property
    def name(self) -> str:
        return str(self.record.get("name", ""))


def _spans_in(document: Mapping[str, Any], locator: str) -> Iterator[Span]:
    for rs in document.get("resourceSpans", []) or []:
        resource = attrs((rs.get("resource") or {}).get("attributes"))
        for ss in rs.get("scopeSpans", []) or []:
            for span in ss.get("spans", []) or []:
                if isinstance(span, Mapping):
                    yield Span(
                        record=span,
                        attributes=attrs(span.get("attributes")),
                        resource=resource,
                        locator=f"{locator}#{span.get('spanId', '?')}",
                    )


def iter_spans(path: Path) -> Iterator[Span]:
    """Spans from one OTLP/JSON document or from JSONL (one document per line)."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        msg = f"cannot read {path}: {exc.strerror or exc}"
        raise TraceImportError(msg) from exc
    text = decode_utf8(raw, locator=str(path))
    try:
        document = json.loads(text)
    except RecursionError as exc:
        msg = f"{path}: JSON nested too deeply"
        raise TraceImportError(msg) from exc
    except ValueError:
        document = None
    if isinstance(document, Mapping):
        yield from _spans_in(document, str(path))
        return
    if document is not None:
        msg = f"{path}: expected an OTLP/JSON object with resourceSpans"
        raise TraceImportError(msg)
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            document = json.loads(line)
        except RecursionError as exc:
            msg = f"{path}:{lineno}: JSON nested too deeply"
            raise TraceImportError(msg) from exc
        except ValueError as exc:
            msg = f"{path}:{lineno}: invalid JSON: {exc}"
            raise TraceImportError(msg) from exc
        if not isinstance(document, Mapping):
            msg = f"{path}:{lineno}: expected an OTLP/JSON object"
            raise TraceImportError(msg)
        yield from _spans_in(document, f"{path}:{lineno}")
