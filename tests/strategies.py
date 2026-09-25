"""Hypothesis strategies for permdiff models."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from hypothesis import strategies as st

from permdiff.models import Agent, Principal, Resource, Tool, ToolCall

_KEY = st.text(min_size=1, max_size=12)
_SCALAR = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**53), max_value=2**53),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=20),
)


def json_values(max_leaves: int = 20) -> st.SearchStrategy[Any]:
    """Arbitrary JSON values, bounded so tests stay fast."""
    return st.recursive(
        _SCALAR,
        lambda inner: st.one_of(
            st.lists(inner, max_size=4), st.dictionaries(_KEY, inner, max_size=4)
        ),
        max_leaves=max_leaves,
    )


def json_objects() -> st.SearchStrategy[dict[str, Any]]:
    return st.dictionaries(_KEY, json_values(), max_size=4)


def aware_datetimes() -> st.SearchStrategy[datetime]:
    offsets = st.integers(min_value=-14 * 60, max_value=14 * 60).map(
        lambda minutes: timezone(timedelta(minutes=minutes))
    )
    return st.datetimes(
        min_value=datetime(2000, 1, 1),
        max_value=datetime(2100, 1, 1),
        timezones=offsets,
    )


def tool_calls() -> st.SearchStrategy[ToolCall]:
    return st.builds(
        ToolCall,
        id=st.text(min_size=1, max_size=40),
        timestamp=aware_datetimes(),
        principal=st.builds(Principal, id=st.text(min_size=1, max_size=40), attrs=json_objects()),
        agent=st.builds(
            Agent,
            id=st.text(min_size=1, max_size=40),
            version=st.none() | st.text(max_size=10),
            attrs=json_objects(),
        ),
        tool=st.builds(Tool, name=st.text(min_size=1, max_size=40)),
        arguments=st.none() | json_objects(),
        resource=st.builds(Resource, attrs=json_objects()),
        context=json_objects(),
    )
