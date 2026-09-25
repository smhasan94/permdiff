"""Trace filters (FR-6): a time window on trace timestamps plus tool/agent/principal globs.

``--since 7d`` is relative to the newest trace timestamp, not the wall clock, so a CI run
on the same corpus always selects the same calls.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from permdiff.errors import ConfigError
from permdiff.models import Frozen, ToolCall

_RELATIVE = re.compile(r"^(?P<n>\d+)(?P<unit>[dhm])$")
_UNITS = {"d": timedelta(days=1), "h": timedelta(hours=1), "m": timedelta(minutes=1)}


def parse_bound(text: str, *, flag: str, newest: datetime | None) -> datetime:
    """``7d``/``12h``/``30m`` back from ``newest``, or an ISO date/datetime (naive means UTC)."""
    cleaned = text.strip()
    if m := _RELATIVE.match(cleaned):
        if newest is None:
            msg = f"{flag} {text!r} is relative but the corpus is empty"
            raise ConfigError(msg)
        return newest - int(m.group("n")) * _UNITS[m.group("unit")]
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError as exc:
        msg = f"{flag} {text!r}: expected 7d, 12h, 30m, or an ISO 8601 date/time"
        raise ConfigError(msg) from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class TraceFilters(Frozen):
    since: str | None = None
    until: str | None = None
    tool: tuple[str, ...] = ()
    agent: tuple[str, ...] = ()
    principal: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not any((self.since, self.until, self.tool, self.agent, self.principal))


class FilterResult(Frozen):
    calls: tuple[ToolCall, ...]
    filtered: int
    window: tuple[datetime, datetime] | None
    """Effective window: the since/until bounds, falling back to the kept calls' extremes."""


def _matches(value: str, patterns: Sequence[str]) -> bool:
    return not patterns or any(fnmatch.fnmatchcase(value, p) for p in patterns)


def apply_filters(calls: Sequence[ToolCall], filters: TraceFilters) -> FilterResult:
    stamps = [c.timestamp for c in calls]
    newest = max(stamps) if stamps else None
    since = parse_bound(filters.since, flag="--since", newest=newest) if filters.since else None
    until = parse_bound(filters.until, flag="--until", newest=newest) if filters.until else None
    if since is not None and until is not None and since > until:
        msg = f"--since {filters.since!r} is after --until {filters.until!r}"
        raise ConfigError(msg)
    kept = tuple(
        c
        for c in calls
        if (since is None or c.timestamp >= since)
        and (until is None or c.timestamp <= until)
        and _matches(c.tool.name, filters.tool)
        and _matches(c.agent.id, filters.agent)
        and _matches(c.principal.id, filters.principal)
    )
    kept_stamps = [c.timestamp for c in kept]
    window: tuple[datetime, datetime] | None = None
    if kept_stamps or since is not None or until is not None:
        start = since if since is not None else (min(kept_stamps) if kept_stamps else None)
        end = until if until is not None else (max(kept_stamps) if kept_stamps else None)
        if start is not None and end is not None:
            window = (start, end)
    return FilterResult(calls=kept, filtered=len(calls) - len(kept), window=window)
