from __future__ import annotations

import pytest

from permdiff.errors import ConfigError
from permdiff.importers.input_map import InputMap, apply, parse_input_map, resolve_source

EVENT = {
    "decision_id": "d-1",
    "timestamp": "2026-09-26T03:29:40.004172Z",
    "path": "http/authz/allow",
    "input": {
        "method": "GET",
        "path": "/salary/bob",
        "user": {"name": "bob", "groups": ["eng", "admins"]},
        "attrs": {"region": "eu"},
    },
}


def test_parse_accepts_pairs_and_comma_joined_specs() -> None:
    parsed = parse_input_map(["principal.id=user.name", "tool.name=method,resource.id=path"])

    assert parsed == InputMap(
        pairs=(("principal.id", "user.name"), ("tool.name", "method"), ("resource.id", "path"))
    )
    assert parse_input_map([]) == InputMap(pairs=())


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ("principal=user", "unknown target 'principal'"),
        ("tool.name", "expected target=source"),
        ("=user", "expected target=source"),
        ("tool.name=", "expected target=source"),
        ("nope.x=y", "unknown target 'nope.x'"),
        ("context=x", "unknown target 'context'"),
    ],
)
def test_parse_rejects_bad_pairs(spec: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_input_map([spec])


def test_parse_rejects_whole_and_keyed_arguments_together() -> None:
    with pytest.raises(ConfigError, match="not both"):
        parse_input_map(["arguments=args", "arguments.k=const:x"])
    with pytest.raises(ConfigError, match="not both"):
        parse_input_map(["arguments.k=const:x", "tool.name=m", "arguments=args"])


def test_parse_rejects_duplicate_targets() -> None:
    with pytest.raises(ConfigError, match=r"tool\.name mapped twice"):
        parse_input_map(["tool.name=method", "tool.name=path"])


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("method", "GET"),
        ("user.name", "bob"),
        ("user.groups.1", "admins"),
        ("user.groups.9", None),
        ("user.missing.deep", None),
        ("event.decision_id", "d-1"),
        ("event.input.user.name", "bob"),
        ("event.nope", None),
        ("const:gateway", "gateway"),
        ("const:", ""),
    ],
)
def test_resolve_source(source: str, expected: object) -> None:
    assert resolve_source(source, input=EVENT["input"], event=EVENT) == expected


def test_apply_builds_a_nested_payload_with_event_defaults() -> None:
    input_map = parse_input_map(
        [
            "principal.id=user.name",
            "principal.attrs.groups=user.groups",
            "agent.id=const:gateway",
            "agent.version=event.path",
            "tool.name=method",
            "resource.type=const:http",
            "resource.id=path",
            "context.region=attrs.region",
            "arguments.path=path",
            "arguments.missing=nope",
        ]
    )

    payload = apply(input_map, input=EVENT["input"], event=EVENT)

    assert payload == {
        "id": "d-1",
        "timestamp": "2026-09-26T03:29:40.004172Z",
        "principal": {"id": "bob", "attrs": {"groups": ["eng", "admins"]}},
        "agent": {"id": "gateway", "version": "http/authz/allow"},
        "tool": {"name": "GET"},
        "resource": {"type": "http", "id": "/salary/bob"},
        "context": {"region": "eu"},
        "arguments": {"path": "/salary/bob"},
    }


def test_apply_lets_explicit_id_timestamp_and_whole_arguments_win() -> None:
    input_map = parse_input_map(
        [
            "id=event.path",
            "timestamp=const:2026-01-01T00:00:00Z",
            "arguments=user",
            "tool.name=method",
        ]
    )

    payload = apply(input_map, input=EVENT["input"], event=EVENT)

    assert payload["id"] == "http/authz/allow"
    assert payload["timestamp"] == "2026-01-01T00:00:00Z"
    assert payload["arguments"] == {"name": "bob", "groups": ["eng", "admins"]}


def test_apply_skips_absent_sources_and_non_object_arguments() -> None:
    input_map = parse_input_map(["tool.name=method", "principal.id=user.email", "arguments=method"])

    payload = apply(input_map, input=EVENT["input"], event=EVENT)

    assert "principal" not in payload
    assert "arguments" not in payload
    assert payload["tool"] == {"name": "GET"}
