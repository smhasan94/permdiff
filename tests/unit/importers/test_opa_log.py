from __future__ import annotations

import json
from pathlib import Path

import pytest

from permdiff.errors import TraceImportError
from permdiff.importers import registry
from permdiff.importers.opa_log import (
    FORMAT_NAME,
    ND_CACHE_CONTEXT_KEY,
    OpaDecisionLogImporter,
    unwrap_result,
)
from permdiff.models import Effect

FIXTURES = Path(__file__).parents[2] / "fixtures" / "opa_log"


@pytest.mark.parametrize("name", ["console.jsonl", "sink.json"])
def test_both_file_shapes_import_the_same_calls(name: str) -> None:
    result = OpaDecisionLogImporter().read(FIXTURES / name)

    assert [c.id for c in result.calls] == ["c1", "c2", "c3"]
    assert result.stats.read == 3
    assert result.stats.skipped == 1
    (reason,) = result.stats.skipped_locators
    assert "input is not a permdiff ToolCall" in reason
    assert "principal" in reason


def test_mapping_of_context_recorded_effect_and_nd_cache() -> None:
    result = OpaDecisionLogImporter().read(FIXTURES / "console.jsonl", strict=False)
    allow, approval, lucky = result.calls

    assert allow.timestamp.isoformat() == "2026-09-25T12:00:00+00:00"  # the call's own time
    assert allow.principal.id == "alice@example.com"
    assert allow.tool.name == "github.read"
    assert allow.recorded.effect == Effect.ALLOW
    assert allow.recorded.policy_hash == "W3sibCI6InN5cy9jYXRhbG9nIn1d"
    assert allow.context["opa.decision_id"] == "88d625cf-f7f3-45a1-ad7a-648b330d8d7e"
    assert allow.context["opa.path"] == "agent/authz/decision"
    assert allow.context["opa.logged_at"] == "2026-09-26T03:49:25.358697Z"
    assert allow.context["opa.labels"] == {"id": "opa-instance-0001", "version": "1.21.0"}
    assert allow.context["opa.bundles"] == {"authz": "W3sibCI6InN5cy9jYXRhbG9nIn1d"}
    assert allow.context["opa.requested_by"] == "10.0.0.5:40000"
    assert ND_CACHE_CONTEXT_KEY not in allow.context
    assert allow.source is not None
    assert allow.source.format == FORMAT_NAME
    assert "console.jsonl:" in allow.source.locator

    assert approval.recorded.effect == Effect.REQUIRE_APPROVAL
    assert approval.recorded.policy_hash is None
    assert "opa.bundles" not in approval.context

    assert lucky.recorded.effect is None
    assert "expected object, boolean, or effect string" in lucky.context["opa.result_unmapped"]
    assert lucky.context[ND_CACHE_CONTEXT_KEY] == {"rand.intn": {'["x",10]': 2}}


def test_sink_locators_index_the_array() -> None:
    result = OpaDecisionLogImporter().read(FIXTURES / "sink.json")

    assert result.calls[0].source is not None
    assert result.calls[0].source.locator.endswith("sink.json[0]")
    assert result.stats.skipped_locators[0].startswith(str(FIXTURES / "sink.json") + "[3]")


def test_decision_option_unwraps_package_results(tmp_path: Path) -> None:
    event = {
        "decision_id": "d-1",
        "path": "agent/authz",
        "input": {
            "id": "c9",
            "timestamp": "2026-09-25T12:00:00Z",
            "principal": {"id": "u"},
            "agent": {"id": "a"},
            "tool": {"name": "t"},
        },
        "result": {"decision": {"effect": "deny", "reason": "nope"}, "lucky": 4},
        "timestamp": "2026-09-26T03:29:40.004172Z",
    }
    path = tmp_path / "log.json"
    path.write_text(json.dumps([event]))

    plain = OpaDecisionLogImporter().read(path).calls[0]
    unwrapped = OpaDecisionLogImporter(decision="data.agent.authz.decision").read(path).calls[0]

    assert plain.recorded.effect is None
    assert "no string 'effect'" in plain.context["opa.result_unmapped"]
    assert unwrapped.recorded.effect == Effect.DENY
    assert "opa.result_unmapped" not in unwrapped.context
    assert unwrap_result({"decision": True}, "decision") is True
    assert unwrap_result({"effect": "allow"}, "data.x.decision") == {"effect": "allow"}
    assert unwrap_result(True, "decision") is True


def test_erased_and_masked_inputs_keep_their_paths(tmp_path: Path) -> None:
    event = {
        "decision_id": "d-2",
        "path": "agent/authz/decision",
        "input": {
            "id": "c10",
            "timestamp": "2026-09-25T12:00:00Z",
            "principal": {"id": "u"},
            "agent": {"id": "a"},
            "tool": {"name": "t"},
            "arguments": {"token": "**REDACTED**"},
        },
        "result": True,
        "erased": ["/input/arguments/password"],
        "masked": ["/input/arguments/token"],
        "timestamp": "2026-09-26T03:29:40Z",
    }
    path = tmp_path / "log.jsonl"
    path.write_text(json.dumps(event) + "\n")

    (call,) = OpaDecisionLogImporter().read(path, strict=True).calls

    assert call.recorded.effect == Effect.ALLOW
    assert call.context["opa.erased"] == ["/input/arguments/password"]
    assert call.context["opa.masked"] == ["/input/arguments/token"]


def test_bad_lines_skip_or_abort_and_non_events_are_silent(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    path.write_text(
        '{"level": "info", "msg": "Initializing server"}\n'
        "{not json\n"
        '{"decision_id": "d-3", "input": 5, "result": true}\n'
        '{"type": "openpolicyagent.org/decision_logs", "decision_id": "d-4", '
        '"input": {}, "result": true}\n'
    )

    lenient = OpaDecisionLogImporter().read(path)
    assert lenient.stats.read == 0
    reasons = [loc.split(": ", 1)[1] for loc in lenient.stats.skipped_locators]
    assert reasons[0].startswith("invalid JSON")
    assert "input is not a permdiff ToolCall" in reasons[1]
    assert "input is not a permdiff ToolCall" in reasons[2]
    assert lenient.stats.skipped == 3

    with pytest.raises(TraceImportError, match=r"log\.jsonl:2"):
        OpaDecisionLogImporter().read(path, strict=True)


def test_array_file_must_hold_objects(tmp_path: Path) -> None:
    path = tmp_path / "log.json"
    path.write_text('{"decision_id": "solo", "input": {}, "result": true}')
    single = OpaDecisionLogImporter().read(path)
    assert single.stats.skipped == 1  # one event object is accepted as a one-event file

    path.write_text("[1, 2]")
    with pytest.raises(TraceImportError, match="expected decision-log events"):
        OpaDecisionLogImporter().read(path)


def test_detect_and_registry() -> None:
    importer = OpaDecisionLogImporter()
    assert importer.detect((FIXTURES / "console.jsonl").read_bytes()[:8192])
    assert importer.detect((FIXTURES / "sink.json").read_bytes()[:8192])
    assert not importer.detect(b'{"schema": "custody.trace.v1"}\n')
    assert not importer.detect(b'{"hook_event_name": "PreToolUse"}\n')
    assert not importer.detect(b"\x1f\x8b\x08")
    assert not importer.detect(b"")

    assert registry.detect(FIXTURES / "console.jsonl").name == FORMAT_NAME
    assert registry.detect(FIXTURES / "sink.json").name == FORMAT_NAME
    assert registry.names()[-1] == FORMAT_NAME
    with_option = registry.get(FORMAT_NAME, decision="data.x.y", principal_from="attr.u")
    assert with_option.decision == "data.x.y"  # type: ignore[attr-defined]
    otel = registry.get("otel", decision="data.x.y", principal_from="attr.u")
    assert otel.principal_from == "attr.u"  # type: ignore[attr-defined]


def test_oversized_console_line_is_skipped_and_counted(tmp_path: Path) -> None:
    from permdiff.models.limits import MAX_LINE_BYTES  # noqa: PLC0415

    big = {"decision_id": "d-big", "input": {"id": "x", "pad": "x" * (MAX_LINE_BYTES + 1)}}
    path = tmp_path / "log.jsonl"
    path.write_text('{"level": "info", "msg": "Initializing server"}\n' + json.dumps(big) + "\n")

    result = OpaDecisionLogImporter().read(path)

    assert result.stats.read == 0
    assert result.stats.skipped == 1
    assert "over the 1 MiB limit" in result.stats.skipped_locators[0]
