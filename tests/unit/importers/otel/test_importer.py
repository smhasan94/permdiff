from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from permdiff.errors import TraceImportError
from permdiff.importers import registry
from permdiff.importers.otel import OtelImporter
from permdiff.importers.otel.spans import iter_spans
from tests.conftest import OPA_FIXTURES

FIXTURES = OPA_FIXTURES.parent / "otel"


def test_reads_otlp_json_document_and_keeps_only_tool_spans() -> None:
    result = OtelImporter().read(FIXTURES / "execute_tool.json", strict=True)

    assert result.stats.read == 3
    assert [c.tool.name for c in result.calls] == ["stripe.refund", "github.read", "slack.post"]
    refund = result.calls[0]
    assert refund.id == "call_refund_1"
    assert refund.timestamp == datetime(2026, 9, 20, 14, 0, 1, tzinfo=UTC)
    assert refund.principal.id == "alice@example.com"  # resource enduser.id
    assert refund.agent.id == "support-bot"
    assert refund.tool.type == "function"
    assert refund.arguments == {"charge_id": "ch_1", "amount": 750}  # JSON string
    assert refund.context["session_id"] == "conv-1"
    assert refund.context["otel.span_id"] == "aaaa000000000002"
    assert refund.source is not None
    assert refund.source.format == "otel.genai"
    assert refund.source.locator.endswith("execute_tool.json#aaaa000000000002")


def test_kvlist_arguments_span_level_principal_and_missing_arguments() -> None:
    calls = OtelImporter().read(FIXTURES / "execute_tool.json").calls

    read = calls[1]
    assert read.arguments == {"repo": "org/repo", "paths": ["a", "b"], "limit": 5, "deep": True}
    assert read.principal.id == "bob@example.com"  # span attribute beats resource
    assert calls[2].arguments is None
    assert calls[2].agent.id == "support-bot"  # resource service.name fallback


def test_reads_jsonl_documents_and_span_name_fallbacks() -> None:
    result = OtelImporter().read(FIXTURES / "execute_tool.jsonl")

    assert result.stats.read == 5  # 3 from line 1 + 2 from line 2
    assert result.stats.skipped == 1  # execute_tool span with no tool name anywhere
    assert "no tool" in result.stats.skipped_locators[0]
    weather, by_name = result.calls[3], result.calls[4]
    assert weather.principal.id == "unknown"
    assert weather.context["otel.principal_missing"] is True
    assert weather.agent.id == "ops-bot"
    assert by_name.tool.name == "by_name_only"  # detected by span name prefix, no operation attr
    assert by_name.source is not None
    assert by_name.source.locator.endswith("execute_tool.jsonl:2#bbbb000000000002")


def test_principal_from_overrides_and_reports_unknown() -> None:
    via_resource = OtelImporter(principal_from="resource.attr.service.name").read(
        FIXTURES / "execute_tool.json"
    )
    via_attr = OtelImporter(principal_from="gen_ai.agent.name").read(FIXTURES / "execute_tool.json")

    assert {c.principal.id for c in via_resource.calls} == {"support-bot"}
    assert via_attr.calls[0].principal.id == "support-bot"
    assert via_attr.calls[2].principal.id == "unknown"


def test_strict_aborts_on_first_unmappable_span() -> None:
    with pytest.raises(TraceImportError, match=r"execute_tool\.jsonl:2#bbbb000000000003"):
        OtelImporter().read(FIXTURES / "execute_tool.jsonl", strict=True)


def test_iter_spans_rejects_non_otlp_and_bad_lines(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(TraceImportError, match="resourceSpans"):
        list(iter_spans(bad))
    badline = tmp_path / "bad.jsonl"
    badline.write_text('{"resourceSpans": []}\n{oops\n', encoding="utf-8")
    with pytest.raises(TraceImportError, match=r"bad\.jsonl:2"):
        list(iter_spans(badline))
    with pytest.raises(TraceImportError, match="cannot read"):
        list(iter_spans(tmp_path / "missing.json"))


def test_detect_and_registry_options() -> None:
    importer = OtelImporter()

    assert importer.detect(b'{\n  "resourceSpans": [')
    assert importer.detect(b'{"resourceSpans":[]}\n')
    assert not importer.detect(b'{"schema": "custody.trace.v1"}')
    assert not importer.detect(b"[]")
    assert isinstance(registry.get("otel"), OtelImporter)
    assert registry.get("otel", principal_from="attr.x").principal_from == "attr.x"  # type: ignore[attr-defined]
    assert isinstance(registry.detect(FIXTURES / "execute_tool.json"), OtelImporter)
    assert registry.names() == ("jsonl", "custody", "otel")


def test_max_records_cap(tmp_path: Path) -> None:
    with pytest.raises(TraceImportError, match="max_records=1"):
        OtelImporter().read(FIXTURES / "execute_tool.json", max_records=1)


def test_start_time_required(tmp_path: Path) -> None:
    doc = json.loads((FIXTURES / "execute_tool.json").read_text(encoding="utf-8"))
    for s in doc["resourceSpans"][0]["scopeSpans"][0]["spans"]:
        s.pop("startTimeUnixNano", None)
    path = tmp_path / "nots.json"
    path.write_text(json.dumps(doc), encoding="utf-8")

    result = OtelImporter().read(path)

    assert result.stats.read == 0
    assert all("startTimeUnixNano" in r for r in result.stats.skipped_locators)
