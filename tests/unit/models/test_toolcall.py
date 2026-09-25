from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from hypothesis import given, settings
from pydantic import ValidationError

from permdiff.models import Effect, Principal, Recorded, ToolCall
from permdiff.models.limits import MAX_NESTING
from tests.strategies import tool_calls

MINIMAL: dict[str, Any] = {
    "id": "call-1",
    "timestamp": "2026-09-20T14:03:11.412Z",
    "principal": {"id": "alice@example.com"},
    "agent": {"id": "support-bot"},
    "tool": {"name": "stripe.refund"},
}


def test_minimal_record_validates_with_defaults() -> None:
    call = ToolCall.model_validate(MINIMAL)

    assert call.principal.type == "user"
    assert call.principal.attrs == {}
    assert call.arguments is None
    assert call.resource.type is None
    assert call.context == {}
    assert call.recorded == Recorded()
    assert call.source is None
    assert call.timestamp == datetime(2026, 9, 20, 14, 3, 11, 412000, tzinfo=UTC)


@pytest.mark.parametrize("missing", ["id", "timestamp", "principal", "agent", "tool"])
def test_missing_required_field_is_rejected_and_named(missing: str) -> None:
    record = {k: v for k, v in MINIMAL.items() if k != missing}

    with pytest.raises(ValidationError) as exc_info:
        ToolCall.model_validate(record)

    assert missing in str(exc_info.value)


@pytest.mark.parametrize(
    ("section", "field"), [("principal", "id"), ("agent", "id"), ("tool", "name")]
)
def test_missing_nested_required_field_is_rejected(section: str, field: str) -> None:
    record = {**MINIMAL, section: {}}

    with pytest.raises(ValidationError) as exc_info:
        ToolCall.model_validate(record)

    assert field in str(exc_info.value)


def test_naive_timestamp_is_rejected() -> None:
    record = {**MINIMAL, "timestamp": "2026-09-20T14:03:11"}

    with pytest.raises(ValidationError, match="timezone"):
        ToolCall.model_validate(record)


def test_extra_fields_are_rejected_at_every_level() -> None:
    with pytest.raises(ValidationError, match="extra"):
        ToolCall.model_validate({**MINIMAL, "bogus": 1})
    with pytest.raises(ValidationError, match="extra"):
        ToolCall.model_validate({**MINIMAL, "tool": {"name": "t", "bogus": 1}})


def test_arguments_attrs_and_context_accept_arbitrary_json() -> None:
    blob = {"n": 1, "f": 1.5, "s": "x", "b": True, "z": None, "l": [1, [2]], "o": {"k": {}}}
    record = {
        **MINIMAL,
        "arguments": blob,
        "context": blob,
        "principal": {"id": "p", "attrs": blob},
        "resource": {"attrs": blob},
    }

    call = ToolCall.model_validate(record)

    assert call.arguments == blob
    assert call.context == blob
    assert call.principal.attrs == blob
    assert call.resource.attrs == blob


def test_nesting_beyond_limit_is_rejected_with_field_name() -> None:
    deep: Any = "leaf"
    for _ in range(MAX_NESTING + 1):
        deep = {"k": deep}

    with pytest.raises(ValidationError, match="nesting"):
        ToolCall.model_validate({**MINIMAL, "arguments": deep})


def test_nesting_at_limit_is_accepted() -> None:
    deep: Any = "leaf"
    for _ in range(MAX_NESTING - 1):  # the enclosing object is the last level
        deep = [deep]

    call = ToolCall.model_validate({**MINIMAL, "context": {"k": deep}})

    assert call.context["k"] is not None


def test_recorded_effect_uses_effect_enum() -> None:
    call = ToolCall.model_validate({**MINIMAL, "recorded": {"effect": "deny"}})

    assert call.recorded.effect is Effect.DENY


def test_model_is_frozen() -> None:
    call = ToolCall.model_validate(MINIMAL)

    with pytest.raises(ValidationError):
        call.id = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        call.principal.id = "other"  # type: ignore[misc]


def test_derived_id_is_stable_and_order_independent() -> None:
    ts = datetime(2026, 9, 20, 14, 3, 11, tzinfo=UTC)

    a = ToolCall.derived_id(ts, "alice", "stripe.refund", {"x": 1, "y": [1, 2]})
    b = ToolCall.derived_id(ts, "alice", "stripe.refund", {"y": [1, 2], "x": 1})
    c = ToolCall.derived_id(ts, "alice", "stripe.refund", {"x": 2})
    d = ToolCall.derived_id(ts, "alice", "stripe.refund", None)

    assert a == b
    assert len(a) == 64
    assert len({a, c, d}) == 3


def test_derived_id_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone"):
        ToolCall.derived_id(datetime(2026, 1, 1), "p", "t", None)


@settings(max_examples=60, deadline=None)
@given(tool_calls())
def test_json_round_trip_preserves_call(call: ToolCall) -> None:
    text = call.model_dump_json()

    assert ToolCall.model_validate_json(text) == call


def test_principal_equality_and_copy_update() -> None:
    p = Principal(id="a")

    q = p.model_copy(update={"type": "service"})

    assert p.type == "user"
    assert q.type == "service"
    assert q.id == "a"
