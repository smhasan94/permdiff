from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from permdiff.errors import ConfigError
from permdiff.importers.filters import TraceFilters, apply_filters, parse_bound
from permdiff.models import ToolCall

T0 = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def _call(i: int, tool: str = "t", agent: str = "bot", principal: str = "alice") -> ToolCall:
    return ToolCall.model_validate(
        {
            "id": f"c{i}",
            "timestamp": (T0 - timedelta(days=i)).isoformat(),
            "principal": {"id": principal},
            "agent": {"id": agent},
            "tool": {"name": tool},
        }
    )


CALLS = [
    _call(0, "github.read"),
    _call(3, "stripe.refund", "ops-bot", "bob"),
    _call(10, "slack.post"),
]


def test_relative_since_is_measured_from_the_newest_trace() -> None:
    assert parse_bound("7d", flag="--since", newest=T0) == T0 - timedelta(days=7)
    assert parse_bound("12h", flag="--since", newest=T0) == T0 - timedelta(hours=12)
    assert parse_bound("30m", flag="--since", newest=T0) == T0 - timedelta(minutes=30)


def test_iso_bounds_accept_dates_and_z_suffix_and_treat_naive_as_utc() -> None:
    assert parse_bound("2026-09-20", flag="--since", newest=None) == datetime(
        2026, 9, 20, tzinfo=UTC
    )
    assert parse_bound("2026-09-20T10:00:00Z", flag="--until", newest=None) == datetime(
        2026, 9, 20, 10, tzinfo=UTC
    )


@pytest.mark.parametrize("bad", ["yesterday", "7 days", "7w", ""])
def test_bad_bounds_name_the_flag(bad: str) -> None:
    with pytest.raises(ConfigError, match="--since"):
        parse_bound(bad, flag="--since", newest=T0)


def test_relative_bound_on_empty_corpus_is_an_error() -> None:
    with pytest.raises(ConfigError, match="empty"):
        apply_filters([], TraceFilters(since="7d"))


def test_since_window_keeps_recent_calls_and_reports_effective_window() -> None:
    result = apply_filters(CALLS, TraceFilters(since="7d"))

    assert [c.id for c in result.calls] == ["c0", "c3"]
    assert result.filtered == 1
    assert result.window == (T0 - timedelta(days=7), T0)


def test_until_and_iso_since_bounds() -> None:
    result = apply_filters(CALLS, TraceFilters(since="2026-09-10", until="2026-09-23"))

    assert [c.id for c in result.calls] == ["c3", "c10"]
    assert result.window == (datetime(2026, 9, 10, tzinfo=UTC), datetime(2026, 9, 23, tzinfo=UTC))


def test_since_after_until_is_an_error() -> None:
    with pytest.raises(ConfigError, match="after --until"):
        apply_filters(CALLS, TraceFilters(since="2026-09-24", until="2026-09-01"))


def test_globs_on_tool_agent_and_principal_combine() -> None:
    by_tool = apply_filters(CALLS, TraceFilters(tool=("github.*", "slack.*")))
    by_agent = apply_filters(CALLS, TraceFilters(agent=("ops-*",)))
    both = apply_filters(CALLS, TraceFilters(tool=("*",), principal=("b?b",)))

    assert [c.id for c in by_tool.calls] == ["c0", "c10"]
    assert [c.id for c in by_agent.calls] == ["c3"]
    assert [c.id for c in both.calls] == ["c3"]
    assert both.filtered == 2


def test_no_filters_keeps_everything_with_window_from_calls() -> None:
    result = apply_filters(CALLS, TraceFilters())

    assert result.filtered == 0
    assert result.window == (T0 - timedelta(days=10), T0)
    assert TraceFilters().is_empty


def test_nothing_kept_gives_no_window_unless_bounds_given() -> None:
    assert apply_filters(CALLS, TraceFilters(tool=("nope",))).window is None
    assert apply_filters(
        CALLS, TraceFilters(tool=("nope",), since="2026-09-01", until="2026-09-02")
    ).window == (
        datetime(2026, 9, 1, tzinfo=UTC),
        datetime(2026, 9, 2, tzinfo=UTC),
    )
