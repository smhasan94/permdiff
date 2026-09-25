from __future__ import annotations

from pathlib import Path

import pytest

from permdiff.errors import TraceImportError
from permdiff.importers import registry
from permdiff.importers.custody import CUSTODY_SCHEMA, CustodyImporter
from permdiff.models import Effect

FIXTURES = Path(__file__).parents[2] / "fixtures" / "custody"


def test_maps_every_action_type_and_verdict() -> None:
    result = CustodyImporter().read(FIXTURES / "all_types.jsonl", strict=True)

    calls = result.calls
    assert result.stats.read == 8
    assert [c.tool.type for c in calls] == [
        "exec",
        "file_read",
        "file_write",
        "file_delete",
        "network",
        "tool_call",
        "mcp_call",
        "llm_call",
    ]
    assert [c.recorded.effect for c in calls] == [
        Effect.DENY,
        Effect.ALLOW,
        Effect.ALLOW,
        Effect.ALLOW,
        Effect.ALLOW,
        Effect.ALLOW,
        Effect.DENY,
        Effect.ALLOW,
    ]
    first = calls[0]
    assert first.id == "01J8Z9CUSTODY00000000000001"
    assert first.principal.id == "sharukh"
    assert first.principal.attrs == {"host": "macbook.local"}
    assert first.agent.id == "claude-code/2.x"
    assert first.tool.name == "Bash"
    assert first.arguments == {"command": "rm -rf ./build"}
    assert first.recorded.policy_hash == "sha256:abc"
    assert first.context["custody.rule_ids"] == ["destructive.filesystem.rm_rf"]
    assert first.context["session_id"] == "sess-0001"
    assert first.context["cwd"] == "/repo"
    assert first.context["custody.digest_only"] is False
    assert first.source is not None
    assert first.source.format == CUSTODY_SCHEMA
    assert first.source.locator.endswith("all_types.jsonl:1")
    assert first.timestamp.tzinfo is not None


def test_warn_and_observe_keep_the_original_verdict_in_context() -> None:
    calls = CustodyImporter().read(FIXTURES / "all_types.jsonl").calls

    assert calls[2].context["custody.verdict"] == "warn"
    assert calls[3].context["custody.verdict"] == "observe"
    assert "custody.verdict" not in calls[1].context
    assert calls[6].tool.server == "mcp"


def test_digest_only_event_has_no_arguments_and_is_flagged() -> None:
    (call,) = CustodyImporter().read(FIXTURES / "digest_only.jsonl").calls

    assert call.arguments is None
    assert call.context["custody.digest_only"] is True
    assert call.context["custody.input_digest"].startswith("sha256:")


def test_unknown_schema_is_rejected_with_locator() -> None:
    result = CustodyImporter().read(FIXTURES / "unknown_schema.jsonl")

    assert result.calls == ()
    assert "unknown schema 'custody.trace.v2'" in result.stats.skipped_locators[0]
    with pytest.raises(TraceImportError, match=r"unknown_schema\.jsonl:1"):
        CustodyImporter().read(FIXTURES / "unknown_schema.jsonl", strict=True)


def test_invalid_events_are_skipped_with_reasons() -> None:
    result = CustodyImporter().read(FIXTURES / "invalid.jsonl")

    assert result.calls == ()
    reasons = result.stats.skipped_locators
    assert "missing required field actor.user" in reasons[0]
    assert "unknown action.type 'teleport'" in reasons[1]
    assert "unknown decision.verdict 'maybe'" in reasons[2]
    assert "invalid JSON" in reasons[3]


def test_detect_and_registry() -> None:
    importer = CustodyImporter()

    assert importer.detect(b'{"schema": "custody.trace.v1", "id": "x"}')
    assert importer.detect(
        b'\n{"schema": "custody.trace.v2"}'
    )  # sniffed as custody, rejected on read
    assert not importer.detect(b'{"id": "x", "timestamp": "t"}')
    assert not importer.detect(b"garbage")
    assert isinstance(registry.get("custody"), CustodyImporter)
    assert isinstance(registry.detect(FIXTURES / "all_types.jsonl"), CustodyImporter)
    assert "custody" in registry.names()


def test_extra_fields_are_ignored(tmp_path: Path) -> None:
    line = (
        '{"schema":"custody.trace.v1","id":"a","ts":"2026-09-20T00:00:00Z","future":1,'
        '"actor":{"agent":"x","user":"u","team":"t"},"action":{"type":"exec","name":"Bash","input_digest":"sha256:0","nested":{"k":1}}}\n'
    )
    path = tmp_path / "c.jsonl"
    path.write_text(line, encoding="utf-8")

    result = CustodyImporter().read(path, strict=True)

    assert result.stats.read == 1
    assert result.calls[0].recorded.effect is None
