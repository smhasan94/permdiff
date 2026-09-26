"""OPA decision-log importer (FR-L4): permdiff-shaped ``input``, recorded ``result``.

Two on-disk shapes, both verified against OPA 1.21.0 on 2026-09-26: the remote sink's JSON
array of events, and console logging (one event per line with ``type ==
"openpolicyagent.org/decision_logs"`` among ordinary log lines). Only events whose ``input``
is a canonical ``ToolCall`` import; anything else is skipped with the first validation
error named, never guessed.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from permdiff.errors import TraceImportError
from permdiff.evaluators.opa.mapping import to_decision
from permdiff.evaluators.opa.ndcache import ND_CACHE_CONTEXT_KEY
from permdiff.importers.base import ImportResult, ImportStats
from permdiff.importers.jsonl import summarize_validation_error
from permdiff.importers.limits import RecordRejected, check_line_size, decode_utf8
from permdiff.models import Effect, ToolCall
from permdiff.models.limits import DEFAULT_MAX_RECORDS

log = logging.getLogger(__name__)

__all__ = [
    "FORMAT_NAME",
    "ND_CACHE_CONTEXT_KEY",
    "OpaDecisionLogImporter",
    "iter_events",
    "to_toolcall",
    "unwrap_result",
]

FORMAT_NAME = "opa-decision-log"
EVENT_TYPE = "openpolicyagent.org/decision_logs"
_GZIP_MAGIC = b"\x1f\x8b"
_DETECT_LINES = 64
"""Console logs open with server start-up lines; look this far for the first event."""
_CONTEXT_KEYS = (
    ("decision_id", "opa.decision_id"),
    ("path", "opa.path"),
    ("timestamp", "opa.logged_at"),
    ("labels", "opa.labels"),
    ("requested_by", "opa.requested_by"),
    ("erased", "opa.erased"),
    ("masked", "opa.masked"),
)


def is_event(obj: Any) -> bool:
    if not isinstance(obj, Mapping):
        return False
    return obj.get("type") == EVENT_TYPE or ("decision_id" in obj and "input" in obj)


def _parse_document(path: Path, text: str) -> Any:
    try:
        return json.loads(text)
    except RecursionError as exc:
        msg = f"{path}: JSON nested too deeply"
        raise TraceImportError(msg) from exc
    except ValueError:
        return None


def iter_events(path: Path) -> Iterator[tuple[Any, str]]:
    """``(event, locator)`` pairs: ``path[i]`` for an array file, ``path:lineno`` for lines.

    Non-event lines (server log noise) are skipped silently; an unparsable line is yielded
    as ``RecordRejected`` for the caller to count or abort on.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        msg = f"cannot read {path}: {exc.strerror or exc}"
        raise TraceImportError(msg) from exc
    if raw.startswith(_GZIP_MAGIC):
        msg = f"{path} is gzip-compressed; decompress the sink payload first"
        raise TraceImportError(msg)
    text = decode_utf8(raw, locator=str(path))
    document = _parse_document(path, text)
    if isinstance(document, list):
        if not all(isinstance(item, Mapping) for item in document):
            msg = f"{path}: expected decision-log events (JSON objects) in the array"
            raise TraceImportError(msg)
        for index, item in enumerate(document):
            yield item, f"{path}[{index}]"
        return
    if isinstance(document, Mapping):
        yield document, f"{path}"
        return
    if document is not None:
        msg = f"{path}: expected decision-log events (a JSON array or one object per line)"
        raise TraceImportError(msg)
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        locator = f"{path}:{lineno}"
        try:
            check_line_size(line.encode("utf-8"))
            obj = json.loads(line)
        except RecordRejected as exc:
            yield exc, locator
            continue
        except (ValueError, RecursionError) as exc:
            yield RecordRejected(f"invalid JSON: {exc}"), locator
            continue
        if is_event(obj):
            yield obj, locator


def unwrap_result(result: Any, decision: str | None) -> Any:
    """A package-shaped result → the value under the decision rule's last segment."""
    if not decision or not isinstance(result, Mapping) or "effect" in result:
        return result
    rule = decision.rstrip(".").rsplit(".", 1)[-1]
    return result.get(rule, result)


def recorded_from_result(call_id: str, result: Any) -> tuple[Effect | None, str | None]:
    """``(effect, reason)``: the effect the runtime recorded, or why it could not be mapped."""
    decision = to_decision(call_id, result)
    if decision.is_error:
        return None, decision.reasons[0] if decision.reasons else "result could not be mapped"
    return decision.effect, None


def _bundles(event: Mapping[str, Any]) -> dict[str, str]:
    bundles = event.get("bundles")
    if not isinstance(bundles, Mapping):
        return {}
    return {
        str(name): str(meta["revision"])
        for name, meta in bundles.items()
        if isinstance(meta, Mapping) and meta.get("revision") not in (None, "")
    }


def to_toolcall(event: Mapping[str, Any], locator: str, *, decision: str | None) -> ToolCall:
    raw_input = event.get("input")
    if not isinstance(raw_input, Mapping):
        msg = (
            f"input is not a permdiff ToolCall: expected an object, got {type(raw_input).__name__}"
        )
        raise RecordRejected(msg)
    try:
        call = ToolCall.model_validate(raw_input)
    except ValidationError as exc:
        msg = f"input is not a permdiff ToolCall: {summarize_validation_error(exc)}"
        raise RecordRejected(msg) from exc
    context: dict[str, Any] = dict(call.context)
    for source, target in _CONTEXT_KEYS:
        if event.get(source) not in (None, "", [], {}):
            context[target] = event[source]
    bundles = _bundles(event)
    if bundles:
        context["opa.bundles"] = bundles
    nd_cache = event.get("nd_builtin_cache")
    if isinstance(nd_cache, Mapping) and nd_cache:
        context[ND_CACHE_CONTEXT_KEY] = dict(nd_cache)
    effect, unmapped = recorded_from_result(call.id, unwrap_result(event.get("result"), decision))
    if unmapped:
        context["opa.result_unmapped"] = unmapped
    recorded = {
        "effect": effect.value if effect else None,
        "policy_hash": next(iter(bundles.values())) if len(bundles) == 1 else None,
    }
    source_ref = {"format": FORMAT_NAME, "locator": locator}
    try:
        return ToolCall.model_validate(
            call.model_dump() | {"context": context, "recorded": recorded, "source": source_ref}
        )
    except ValidationError as exc:
        raise RecordRejected(summarize_validation_error(exc)) from exc


class OpaDecisionLogImporter:
    name = FORMAT_NAME

    def __init__(self, decision: str | None = None) -> None:
        self.decision = decision

    def detect(self, head: bytes) -> bool:
        """An event among the first lines (console logs start with server noise), or an array."""
        if head.startswith(_GZIP_MAGIC):
            return False
        stripped = head.lstrip()
        if stripped.startswith(b"["):
            return is_event(_leading_object(stripped[1:].lstrip()))
        for line in stripped.splitlines()[:_DETECT_LINES]:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                return False
            if is_event(obj):
                return True
        return False

    def read(
        self, path: Path, *, strict: bool = False, max_records: int = DEFAULT_MAX_RECORDS
    ) -> ImportResult:
        calls: list[ToolCall] = []
        skipped: list[str] = []
        for item, locator in iter_events(path):
            try:
                if isinstance(item, RecordRejected):
                    raise item
                calls.append(to_toolcall(item, locator, decision=self.decision))
            except RecordRejected as exc:
                message = f"{locator}: {exc.reason}"
                if strict:
                    raise TraceImportError(message) from exc
                log.warning("skipping %s", message)
                skipped.append(message)
                continue
            if len(calls) > max_records:
                msg = f"{locator}: corpus exceeds max_records={max_records}"
                raise TraceImportError(msg)
        stats = ImportStats(read=len(calls), skipped=len(skipped), skipped_locators=tuple(skipped))
        return ImportResult(calls=tuple(calls), stats=stats)


def _leading_object(data: bytes) -> Any:
    """The first JSON object in ``data`` when the file is pretty-printed (multi-line)."""
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(data.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    return obj
