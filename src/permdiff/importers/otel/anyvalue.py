"""OTLP/JSON ``AnyValue`` decoding (protobuf JSON mapping)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any


def _int(raw: Any) -> Any:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return raw


def _array(raw: Any) -> list[Any]:
    return [decode(v) for v in (raw or {}).get("values", [])]


def _kvlist(raw: Any) -> dict[str, Any]:
    return attrs((raw or {}).get("values", []))


_DECODERS: tuple[tuple[str, Callable[[Any], Any]], ...] = (
    ("stringValue", lambda v: v),
    ("boolValue", bool),
    ("intValue", _int),  # protobuf JSON carries int64 as a string
    ("doubleValue", lambda v: v),
    ("arrayValue", _array),
    ("kvlistValue", _kvlist),
    ("bytesValue", lambda v: v),  # base64 text; permdiff never interprets it
)


def decode(value: Any) -> Any:
    """``{"stringValue": ...}`` and friends to plain JSON."""
    if not isinstance(value, Mapping):
        return value
    for key, convert in _DECODERS:
        if key in value:
            return convert(value[key])
    return dict(value)


def attrs(items: Sequence[Mapping[str, Any]] | None) -> dict[str, Any]:
    """``[{"key": k, "value": AnyValue}, ...]`` to a plain dict; later keys win."""
    result: dict[str, Any] = {}
    for item in items or ():
        if isinstance(item, Mapping) and "key" in item:
            result[str(item["key"])] = decode(item.get("value"))
    return result
