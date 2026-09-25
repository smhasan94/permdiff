"""Arguments for tool spans that lack ``gen_ai.tool.call.arguments`` (AC-4.3, AC-4.4).

The parent inference span may carry Opt-In ``gen_ai.output.messages`` whose assistant
parts include ``{"type": "tool_call", "id", "name", "arguments"}``. Older instrumentations
emitted a ``gen_ai.choice`` span event with the OpenAI-style ``message.tool_calls`` list.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from typing import Any

from permdiff.importers.otel.anyvalue import attrs
from permdiff.importers.otel.spans import Span

MAX_ANCESTORS = 5
CHOICE_EVENT = "gen_ai.choice"


def _as_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _tool_call_parts(messages: Any) -> Iterator[tuple[str | None, str | None, Any]]:
    """``(id, name, arguments)`` for every ``tool_call`` part in ``gen_ai.*.messages``."""
    for message in _as_json(messages) or []:
        if not isinstance(message, Mapping):
            continue
        for part in message.get("parts") or []:
            if isinstance(part, Mapping) and part.get("type") == "tool_call":
                yield part.get("id"), part.get("name"), part.get("arguments")


def _choice_event_calls(span: Span) -> Iterator[tuple[str | None, str | None, Any]]:
    """Deprecated ``gen_ai.choice`` events: ``message.tool_calls[].function.{name,arguments}``."""
    for event in span.record.get("events") or []:
        if not isinstance(event, Mapping) or event.get("name") != CHOICE_EVENT:
            continue
        for value in attrs(event.get("attributes")).values():
            body = _as_json(value)
            if not isinstance(body, Mapping):
                continue
            raw_message = body.get("message")
            message: Mapping[str, Any] = raw_message if isinstance(raw_message, Mapping) else body
            for call in message.get("tool_calls") or []:
                if not isinstance(call, Mapping):
                    continue
                raw_function = call.get("function")
                function: Mapping[str, Any] = (
                    raw_function if isinstance(raw_function, Mapping) else {}
                )
                yield call.get("id"), function.get("name"), function.get("arguments")


def _candidates(span: Span) -> Iterator[tuple[str | None, str | None, Any]]:
    yield from _tool_call_parts(span.attributes.get("gen_ai.output.messages"))
    yield from _choice_event_calls(span)


def ancestors(span: Span, by_id: Mapping[str, Span]) -> Iterator[Span]:
    current, depth = span, 0
    while current.parent_id and current.parent_id in by_id and depth < MAX_ANCESTORS:
        current = by_id[current.parent_id]
        depth += 1
        yield current


def find_arguments(span: Span, by_id: Mapping[str, Span], *, call_id: str | None, tool: str) -> Any:
    """Arguments from the nearest ancestor: by call id first, else a unique part for the tool."""
    for parent in ancestors(span, by_id):
        candidates = list(_candidates(parent))
        if call_id:
            for cid, _name, arguments in candidates:
                if cid == call_id:
                    return arguments
        by_name = [arguments for _cid, name, arguments in candidates if name == tool]
        if len(by_name) == 1:
            return by_name[0]
    return None
