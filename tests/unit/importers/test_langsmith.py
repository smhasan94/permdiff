from __future__ import annotations

from pathlib import Path

import pytest

from permdiff.importers import registry
from permdiff.importers.langsmith import FORMAT_NAME, LangsmithImporter

FIXTURES = Path(__file__).parents[2] / "fixtures" / "langsmith"


@pytest.mark.parametrize("name", ["runs.jsonl", "runs.parquet"])
def test_tool_runs_become_calls(name: str) -> None:
    if name.endswith(".parquet"):
        pytest.importorskip("pyarrow")
    result = LangsmithImporter().read(FIXTURES / name, strict=True)

    assert [c.tool.name for c in result.calls] == ["github.read", "stripe.refund"]
    assert result.stats.skipped == 0
    read, refund = result.calls

    assert read.id == "b2f7d1c0-0000-4000-8000-000000000001"
    assert read.timestamp.isoformat() == "2026-09-20T10:00:00.123000+00:00"  # naive → UTC
    assert read.principal.id == "alice@example.com"  # extra.metadata.user_id
    assert read.agent.id == "project-uuid-1"
    assert read.arguments == {"repo": "acme/api", "path": "README.md"}
    assert read.context["trace_id"] == "5e0c6e1a-0000-4000-8000-0000000000aa"
    assert read.context["langsmith.parent_run_id"] == "5e0c6e1a-0000-4000-8000-0000000000aa"
    assert read.context["langsmith.tags"] == ["support"]
    assert read.context["langsmith.status"] == "success"
    assert read.context["langsmith.metadata"] == {"user_id": "alice@example.com", "env": "prod"}
    assert read.context["langsmith.outputs"] == {"ok": True}
    assert read.source is not None
    assert read.source.format == FORMAT_NAME

    assert refund.timestamp.isoformat() == "2026-09-20T11:30:00+00:00"
    assert refund.arguments == {"amount": 900, "customer": "cus_123"}  # JSON text
    assert refund.principal.id == "unknown"
    assert refund.context["langsmith.principal_missing"] is True
    assert refund.context["langsmith.error"] == "Timeout"
    assert refund.context["langsmith.status"] == "error"
    assert "langsmith.metadata" not in refund.context


def test_principal_from_overrides_the_default_path() -> None:
    result = LangsmithImporter(principal_from="extra.metadata.env").read(FIXTURES / "runs.jsonl")

    assert result.calls[0].principal.id == "prod"
    assert result.calls[1].principal.id == "unknown"


def test_bad_rows_skip_or_abort(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    path.write_text(
        '{"id": "x", "run_type": "tool", "name": "t"}\n'
        '{"id": "y", "run_type": "tool", "start_time": "2026-09-20T10:00:00"}\n'
        '{"id": "z", "run_type": "tool", "name": "t", '
        '"start_time": "2026-09-20T10:00:00", "inputs": 5}\n'
    )

    lenient = LangsmithImporter().read(path)

    assert lenient.stats.read == 0
    reasons = [loc.split(": ", 1)[1] for loc in lenient.stats.skipped_locators]
    assert "start_time" in reasons[0]
    assert "name" in reasons[1]
    assert "inputs" in reasons[2]


def test_detect_and_registry() -> None:
    importer = LangsmithImporter()
    assert importer.detect((FIXTURES / "runs.jsonl").read_bytes()[:8192])
    assert not importer.detect(
        (Path(__file__).parents[2] / "fixtures" / "langfuse" / "observations.jsonl").read_bytes()[
            :8192
        ]
    )

    assert registry.detect(FIXTURES / "runs.jsonl").name == FORMAT_NAME
    assert registry.names()[-2:] == ("langfuse", "langsmith")
