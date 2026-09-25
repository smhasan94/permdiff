from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from permdiff import schemas

CHECKED_IN = Path(schemas.__file__).parent


@pytest.mark.parametrize("name", schemas.SCHEMA_NAMES)
def test_checked_in_schema_matches_generated(name: str) -> None:
    generated = schemas.json_schema(name)

    on_disk = json.loads((CHECKED_IN / f"{name}.json").read_text(encoding="utf-8"))

    assert on_disk == generated, (
        f"schema drift: regenerate with `permdiff schema {name} > src/permdiff/schemas/{name}.json`"
    )


@pytest.mark.parametrize("name", schemas.SCHEMA_NAMES)
def test_schema_is_valid_draft_2020_12(name: str) -> None:
    schema = schemas.json_schema(name)

    jsonschema.Draft202012Validator.check_schema(schema)

    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["$id"].endswith(f"/{name}.schema.json")


def test_toolcall_schema_accepts_overview_example_and_rejects_missing_tool() -> None:
    schema = schemas.json_schema("toolcall")
    example = {
        "id": "01J8Z9EXAMPLEULID0000000000",
        "timestamp": "2026-09-20T14:03:11.412Z",
        "principal": {"id": "alice@example.com", "type": "user", "attrs": {"department": "s"}},
        "agent": {"id": "support-bot", "version": "1.4.0", "attrs": {}},
        "tool": {"name": "stripe.refund", "server": "stripe-mcp", "type": "function"},
        "arguments": {"charge_id": "ch_3Nx", "amount": 750, "reason": "duplicate"},
        "resource": {"type": "stripe.charge", "id": "ch_3Nx", "attrs": {"currency": "usd"}},
        "context": {"session_id": "sess-9f2", "env": "prod"},
        "recorded": {"effect": "allow", "policy_hash": "sha256:abc"},
        "source": {"format": "custody.trace.v1", "locator": "traces/x.jsonl:1187"},
    }

    jsonschema.validate(example, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({k: v for k, v in example.items() if k != "tool"}, schema)


def test_unknown_schema_name_is_an_error() -> None:
    with pytest.raises(KeyError, match="report"):
        schemas.json_schema("report")


def test_schema_text_is_deterministic_and_newline_terminated() -> None:
    a = schemas.schema_text("decision")
    b = schemas.schema_text("decision")

    assert a == b
    assert a.endswith("\n")
    assert json.loads(a)["title"] == "Decision"
