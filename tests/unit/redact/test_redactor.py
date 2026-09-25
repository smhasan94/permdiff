from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

import pytest
from hypothesis import given, settings

from permdiff.models import (
    Counts,
    Decision,
    Effect,
    Report,
    ReportHeader,
    ToolCall,
    Transition,
)
from permdiff.redact import RedactLevel, Redactor, new_salt, placeholder
from tests.redaction_harness import SENTINELS, assert_no_sentinels
from tests.strategies import json_values, tool_calls

SALT = bytes(range(16))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("hello", "<str:5>"),
        ("", "<str:0>"),
        (42, "<int>"),
        (1.5, "<float>"),
        (True, "<bool>"),
        (False, "<bool>"),
        (None, "<null>"),
        ([1, "ab"], ["<int>", "<str:2>"]),
        ({"k": {"n": [None]}}, {"k": {"n": ["<null>"]}}),
        ((1, 2), ["<int>", "<int>"]),
        (b"raw", "<bytes>"),
    ],
)
def test_placeholder_by_type(value: Any, expected: Any) -> None:
    assert placeholder(value) == expected


def test_placeholder_keeps_keys_and_shape_only() -> None:
    out = placeholder({"charge_id": "ch_3Nx", "amount": 750, "meta": {"tags": ["a", "bb"]}})

    assert out == {
        "charge_id": "<str:6>",
        "amount": "<int>",
        "meta": {"tags": ["<str:1>", "<str:2>"]},
    }


def test_principal_hash_is_stable_for_a_salt_and_differs_across_salts() -> None:
    a = Redactor(salt=SALT)
    b = Redactor(salt=bytes(16))

    assert a.principal_hash("alice") == a.principal_hash("alice")
    assert a.principal_hash("alice") != a.principal_hash("bob")
    assert a.principal_hash("alice") != b.principal_hash("alice")
    assert a.principal_hash("alice").startswith("principal:")
    assert len(a.principal_hash("alice")) == len("principal:") + 8


def test_default_salt_is_fresh_per_redactor() -> None:
    assert Redactor().salt != Redactor().salt
    assert len(new_salt()) == 16
    assert Redactor(salt=SALT).salt_hex == SALT.hex()


def test_safe_call_redacts_values_and_keeps_policy_keys(
    sentinel_corpus: tuple[ToolCall, ...],
) -> None:
    call = sentinel_corpus[0]

    out = Redactor(salt=SALT).call(call)

    assert out.tool == call.tool
    assert out.agent.id == call.agent.id
    assert out.resource.type == call.resource.type
    assert out.timestamp == call.timestamp
    assert out.id == call.id
    assert out.principal.id == Redactor(salt=SALT).principal_hash(call.principal.id)
    assert out.principal.attrs == {"department": f"<str:{len(SENTINELS['principal_attr'])}>"}
    assert out.agent.attrs == {"owner": f"<str:{len(SENTINELS['agent_attr'])}>"}
    assert out.arguments is not None
    assert out.arguments["amount"] == "<int>"
    assert out.arguments["meta"] == {
        "note": f"<str:{len(SENTINELS['arg_nested'])}>",
        "tags": [f"<str:{len(SENTINELS['arg_in_list'])}>", "<int>"],
    }
    assert out.resource.id == f"<str:{len(SENTINELS['resource_id'])}>"
    assert out.context == {"cwd": f"<str:{len(SENTINELS['context'])}>", "env": "<str:4>"}
    assert_no_sentinels(out.model_dump_json())


def test_show_args_reveals_only_listed_top_level_keys(
    sentinel_corpus: tuple[ToolCall, ...],
) -> None:
    out = Redactor(salt=SALT, show_args=frozenset({"charge_id", "amount"})).call(sentinel_corpus[0])

    assert out.arguments is not None
    assert out.arguments["charge_id"] == SENTINELS["arg_top"]
    assert out.arguments["amount"] == 750
    assert out.arguments["meta"]["note"] == f"<str:{len(SENTINELS['arg_nested'])}>"
    assert_no_sentinels(out.model_dump_json(), exclude=("arg_top",))


def test_show_principal_keeps_the_id_and_redacts_the_rest(
    sentinel_corpus: tuple[ToolCall, ...],
) -> None:
    out = Redactor(salt=SALT, show_principal=True).call(sentinel_corpus[0])

    assert out.principal.id == SENTINELS["principal_id"]
    assert_no_sentinels(out.model_dump_json(), exclude=("principal_id",))


def test_none_level_is_the_identity(sentinel_corpus: tuple[ToolCall, ...]) -> None:
    r = Redactor(level=RedactLevel.NONE, salt=SALT)
    call = sentinel_corpus[0]

    assert r.call(call) is call
    assert r.value({"a": 1}) == {"a": 1}
    assert r.arguments(call.arguments) is call.arguments


def test_absent_arguments_and_resource_id_stay_absent() -> None:
    call = ToolCall.model_validate(
        {
            "id": "c",
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            "principal": {"id": "p"},
            "agent": {"id": "a"},
            "tool": {"name": "t"},
        }
    )

    out = Redactor(salt=SALT).call(call)

    assert out.arguments is None
    assert out.resource.id is None


@settings(max_examples=40, deadline=None)
@given(tool_calls())
def test_redaction_never_mutates_the_input(call: ToolCall) -> None:
    before = copy.deepcopy(call.model_dump())

    Redactor(salt=SALT).call(call)

    assert call.model_dump() == before


@settings(max_examples=60, deadline=None)
@given(json_values())
def test_placeholder_output_contains_no_input_strings(value: Any) -> None:
    out = placeholder(value)

    def strings(v: Any) -> set[str]:
        if isinstance(v, dict):
            return set().union(*(strings(x) for x in v.values())) if v else set()
        if isinstance(v, list):
            return set().union(*(strings(x) for x in v)) if v else set()
        return {v} if isinstance(v, str) else set()

    leaked = {s for s in strings(value) if len(s) > 2 and not s.startswith("<")}
    assert leaked.isdisjoint(strings(out))


def _report(calls: tuple[ToolCall, ...]) -> Report:
    transitions = tuple(
        Transition.build(
            c,
            Decision(call_id=c.id, effect=Effect.DENY, engine="e"),
            Decision(call_id=c.id, effect=Effect.ALLOW, engine="e"),
        )
        for c in calls
    )
    header = ReportHeader(
        base_label="main",
        base_sha="a" * 40,
        head_label="HEAD",
        head_sha="b" * 40,
        is_worktree=False,
        policy_path="policy",
        engine="e",
        salt=SALT.hex(),
        generated_at=datetime(2026, 9, 25, tzinfo=UTC),
    )
    return Report(
        header=header,
        transitions=transitions,
        counts=Counts(evaluated=len(calls), by_class={"widening": len(calls)}),
    )


def test_report_redaction_covers_every_transition_and_keeps_header(
    sentinel_corpus: tuple[ToolCall, ...],
) -> None:
    report = _report(sentinel_corpus)

    out = Redactor(salt=SALT).report(report)

    assert out.header == report.header
    assert out.counts == report.counts
    assert len(out.transitions) == len(report.transitions)
    assert all(
        t.base == o.base and t.head == o.head
        for t, o in zip(report.transitions, out.transitions, strict=True)
    )
    assert_no_sentinels(out.model_dump_json())
    assert Redactor(level=RedactLevel.NONE).report(report) is report
    assert (
        Redactor(level=RedactLevel.NONE).transition(report.transitions[0]) is report.transitions[0]
    )
