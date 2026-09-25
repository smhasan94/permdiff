from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from permdiff.evaluators.opa.shim import (
    CASES_ROOT,
    NdOverride,
    render_cases,
    render_shim,
    timestamp_ns,
    validate_decision_path,
)
from permdiff.models import ToolCall


def _call(call_id: str, ts: datetime) -> ToolCall:
    return ToolCall.model_validate(
        {
            "id": call_id,
            "timestamp": ts.isoformat(),
            "principal": {"id": "p"},
            "agent": {"id": "a"},
            "tool": {"name": "t"},
            "arguments": {"n": 1},
        }
    )


def test_shim_binds_input_and_clock_per_case() -> None:
    text = render_shim("data.agent.authz.decision")

    assert "package permdiff" in text
    assert "import rego.v1" in text
    assert f"some c in data.{CASES_ROOT}" in text
    assert "v := data.agent.authz.decision with input as c.call with time.now_ns as c.ts_ns" in text
    assert 'r := {"id": c.id, "value": v}' in text


def test_shim_with_nd_overrides_mocks_each_builtin() -> None:
    text = render_shim("data.p.d", nd_overrides=(NdOverride(builtin="http.send"),))

    assert "with http.send as permdiff_mock_http_send" in text
    assert 'data.permdiff_nd["http.send"][json.marshal(args)]' in text
    assert "permdiff-nd-miss:http.send:" in text


@pytest.mark.parametrize("bad", ["agent.authz", "data", "data.", "data.x y", "data.x.y; drop", ""])
def test_invalid_decision_paths_are_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="--decision"):
        validate_decision_path(bad)


def test_timestamp_ns_is_utc_and_microsecond_precise() -> None:
    ts = datetime(2026, 9, 20, 14, 0, 0, 123456, tzinfo=timezone(timedelta(hours=2)))

    assert timestamp_ns(_call("c", ts)) == int(ts.astimezone(UTC).timestamp()) * 10**9 + 123456000


def test_cases_document_shape() -> None:
    ts = datetime(2026, 9, 20, 14, tzinfo=UTC)

    doc = json.loads(render_cases([_call("a", ts), _call("b", ts)]))

    assert list(doc) == [CASES_ROOT]
    assert [c["id"] for c in doc[CASES_ROOT]] == ["a", "b"]
    assert doc[CASES_ROOT][0]["ts_ns"] == int(ts.timestamp()) * 10**9
    assert doc[CASES_ROOT][0]["call"]["tool"]["name"] == "t"
    assert doc[CASES_ROOT][0]["call"]["timestamp"].startswith("2026-09-20T14:00:00")
