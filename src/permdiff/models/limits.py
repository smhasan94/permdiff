"""Size limits shared by models and importers (AC-1.4)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MAX_LINE_BYTES = 1 << 20
"""Largest accepted JSONL line: 1 MiB."""

MAX_NESTING = 32
"""Deepest accepted nesting of arrays and objects inside JSON fields."""

DEFAULT_MAX_RECORDS = 1_000_000
"""Default cap on records per corpus; configurable by the caller."""


def nesting_depth(value: Any) -> int:
    """Depth of nested containers; scalars are 0, ``{"a": [1]}`` is 2."""
    if isinstance(value, Mapping):
        return 1 + max((nesting_depth(v) for v in value.values()), default=0)
    if isinstance(value, list | tuple):
        return 1 + max((nesting_depth(v) for v in value), default=0)
    return 0


def check_nesting(value: Any, *, limit: int = MAX_NESTING) -> Any:
    """Return ``value`` unchanged, or raise ``ValueError`` when nested too deeply."""
    depth = nesting_depth(value)
    if depth > limit:
        msg = f"nesting depth {depth} exceeds limit {limit}"
        raise ValueError(msg)
    return value
