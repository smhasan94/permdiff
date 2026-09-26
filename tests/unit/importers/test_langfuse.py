from __future__ import annotations

from pathlib import Path

import pytest

from permdiff.importers import registry
from permdiff.importers.langfuse import FORMAT_NAME, LangfuseImporter

FIXTURES = Path(__file__).parents[2] / "fixtures" / "langfuse"


@pytest.mark.parametrize("name", ["observations.jsonl", "observations.jsonl.gz"])
def test_blob_export_tool_observations_become_calls(name: str) -> None:
    result = LangfuseImporter().read(FIXTURES / name, strict=True)

    assert [c.id for c in result.calls] == ["obs-tool-1", "obs-tool-2", "obs-tool-3"]
    assert result.stats.skipped == 0
    read, refund, post = result.calls

    assert read.timestamp.isoformat() == "2026-09-20T10:00:00+00:00"
    assert read.principal.id == "alice@example.com"
    assert read.agent.id == "support-agent"
    assert read.agent.version == "1.2.0"
    assert read.tool.name == "github.read"
    assert read.arguments == {"repo": "acme/api", "path": "README.md"}
    assert read.context["trace_id"] == "trace-1"
    assert read.context["session_id"] == "sess-1"
    assert read.context["langfuse.parent_observation_id"] == "obs-agent-1"
    assert read.context["langfuse.environment"] == "production"
    assert read.context["langfuse.level"] == "DEFAULT"
    assert read.context["langfuse.project_id"] == "proj-1"
    assert read.context["langfuse.metadata"] == {"team": "support"}
    assert read.context["langfuse.output"] == {"ok": True}
    assert read.source is not None
    assert read.source.format == FORMAT_NAME

    assert refund.arguments == {"amount": 900, "customer": "cus_123"}  # already an object
    assert refund.principal.id == "unknown"
    assert refund.context["langfuse.principal_missing"] is True
    assert refund.agent.id == "langfuse"  # no trace name
    assert "session_id" not in refund.context

    assert post.arguments == {"_raw": "not json at all"}
    assert "langfuse.metadata" not in post.context


def test_api_page_with_camel_case_keys() -> None:
    result = LangfuseImporter().read(FIXTURES / "observations_api.json", strict=True)

    (call,) = result.calls
    assert call.id == "obs-tool-1"
    assert call.principal.id == "alice@example.com"
    assert call.agent.id == "support-agent"
    assert call.agent.version == "v1.2.0"  # release
    assert call.context["trace_id"] == "trace-1"
    assert call.context["langfuse.tags"] == ["support"]
    assert call.source is not None
    assert call.source.locator.endswith("observations_api.json[0]")


def test_principal_from_dotted_path_and_bad_rows(tmp_path: Path) -> None:
    via_metadata = LangfuseImporter(principal_from="metadata.team").read(
        FIXTURES / "observations.jsonl"
    )
    assert via_metadata.calls[0].principal.id == "support"
    assert via_metadata.calls[1].principal.id == "unknown"

    path = tmp_path / "bad.jsonl"
    path.write_text(
        '{"id": "x", "type": "TOOL", "name": "t"}\n'
        '{"id": "y", "type": "TOOL", "start_time": "2026-09-20T10:00:00Z"}\n'
        "{oops\n"
    )
    lenient = LangfuseImporter().read(path)
    assert lenient.stats.read == 0
    reasons = [loc.split(": ", 1)[1] for loc in lenient.stats.skipped_locators]
    assert "start_time" in reasons[0]
    assert "name" in reasons[1]
    assert "invalid JSON" in reasons[2]


def test_detect_and_registry() -> None:
    importer = LangfuseImporter()
    assert importer.detect((FIXTURES / "observations.jsonl").read_bytes()[:8192])
    assert importer.detect((FIXTURES / "observations_api.json").read_bytes()[:8192])
    assert not importer.detect(b'{"run_type": "tool", "trace_id": "x"}\n')
    assert not importer.detect(b'{"schema": "custody.trace.v1"}\n')

    assert registry.detect(FIXTURES / "observations.jsonl").name == FORMAT_NAME
    assert registry.detect(FIXTURES / "observations_api.json").name == FORMAT_NAME
    assert registry.get(FORMAT_NAME, principal_from="metadata.x").principal_from == "metadata.x"  # type: ignore[attr-defined]
