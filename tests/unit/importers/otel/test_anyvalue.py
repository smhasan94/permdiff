from __future__ import annotations

from typing import Any

import pytest

from permdiff.importers.otel.anyvalue import attrs, decode


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"stringValue": "x"}, "x"),
        ({"boolValue": True}, True),
        ({"intValue": "42"}, 42),
        ({"intValue": "not-int"}, "not-int"),
        ({"doubleValue": 1.5}, 1.5),
        ({"arrayValue": {"values": [{"stringValue": "a"}, {"intValue": "2"}]}}, ["a", 2]),
        ({"arrayValue": {}}, []),
        ({"kvlistValue": {"values": [{"key": "k", "value": {"stringValue": "v"}}]}}, {"k": "v"}),
        ({"bytesValue": "AQID"}, "AQID"),
        ({"unknownValue": 1}, {"unknownValue": 1}),
        ("plain", "plain"),
        (None, None),
    ],
)
def test_decode(value: Any, expected: Any) -> None:
    assert decode(value) == expected


def test_attrs_builds_a_dict_and_last_key_wins() -> None:
    items: list[dict[str, Any]] = [
        {"key": "a", "value": {"stringValue": "1"}},
        {"key": "a", "value": {"stringValue": "2"}},
        {"novalue": True},
        {"key": "b"},
    ]

    assert attrs(items) == {"a": "2", "b": None}
    assert attrs(None) == {}
