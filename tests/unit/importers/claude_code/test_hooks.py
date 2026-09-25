from __future__ import annotations

from pathlib import Path

import pytest

from permdiff.errors import TraceImportError
from permdiff.importers import registry
from permdiff.importers.claude_code import FORMAT_HOOKS, ClaudeCodeHooksImporter

FIXTURES = Path(__file__).parents[3] / "fixtures" / "claude_code"


def test_reads_pre_tool_use_lines_and_skips_other_events() -> None:
    result = ClaudeCodeHooksImporter().read(FIXTURES / "hooks.jsonl", strict=True)

    assert result.stats.read == 2
    assert result.stats.skipped == 0
    bash, mcp = result.calls

    assert bash.timestamp.isoformat() == "2026-09-25T08:48:25+00:00"
    assert bash.tool.name == "Bash"
    assert bash.arguments == {"command": "ls", "description": "List files"}
    assert bash.agent.id == "claude-code"
    assert bash.agent.version is None
    assert bash.resource.type == "shell"
    assert bash.recorded.effect is None
    assert bash.context["session_id"] == "sess-0001"
    assert bash.context["cwd"] == "/home/dev/project"
    assert bash.context["permission_mode"] == "default"
    assert bash.context["claude_code.principal_missing"] is True
    assert bash.principal.id == "unknown"
    assert bash.source is not None
    assert bash.source.format == FORMAT_HOOKS
    assert bash.source.locator.endswith("hooks.jsonl:1")

    assert mcp.tool.name == "mcp__github__create_issue"
    assert mcp.tool.server == "github"
    assert mcp.context["claude_code.agent_id"] == "a20ee8686ca95262a"
    assert mcp.context["claude_code.agent_type"] == "Explore"
    assert mcp.context["permission_mode"] == "acceptEdits"
    assert mcp.source is not None
    assert mcp.source.locator.endswith("hooks.jsonl:3")


def test_hook_ids_are_tool_use_id_or_derived(tmp_path: Path) -> None:
    result = ClaudeCodeHooksImporter().read(FIXTURES / "hooks.jsonl", strict=True)
    assert result.calls[0].id == "toolu_01"

    path = tmp_path / "hooks.jsonl"
    path.write_text(
        '{"hook_event_name": "PreToolUse", "session_id": "s", "tool_name": "Read", '
        '"tool_input": {"file_path": "/p/a"}, "ts": "2026-09-25T08:48:25Z"}\n'
    )
    (derived,) = ClaudeCodeHooksImporter().read(path, strict=True).calls
    assert len(derived.id) == 64


def test_missing_ts_is_rejected_with_the_documented_hook_named() -> None:
    lenient = ClaudeCodeHooksImporter().read(FIXTURES / "hooks_no_ts.jsonl")

    assert lenient.stats.read == 0
    assert lenient.stats.skipped == 1
    assert "no ts" in lenient.stats.skipped_locators[0]
    assert "jq" in lenient.stats.skipped_locators[0]

    with pytest.raises(TraceImportError, match="jq"):
        ClaudeCodeHooksImporter().read(FIXTURES / "hooks_no_ts.jsonl", strict=True)


def test_principal_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERMDIFF_USER", "dev-user")

    result = ClaudeCodeHooksImporter(principal_from="env:PERMDIFF_USER").read(
        FIXTURES / "hooks.jsonl"
    )

    assert {c.principal.id for c in result.calls} == {"dev-user"}
    assert all("claude_code.principal_missing" not in c.context for c in result.calls)


def test_rejects_non_object_and_missing_fields(tmp_path: Path) -> None:
    path = tmp_path / "hooks.jsonl"
    path.write_text(
        "[1]\n"
        '{"hook_event_name": "PreToolUse", "ts": "2026-09-25T08:48:25Z"}\n'
        '{"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": "ls", '
        '"ts": "2026-09-25T08:48:25Z"}\n'
    )

    result = ClaudeCodeHooksImporter().read(path)

    assert result.stats.read == 0
    reasons = [loc.split(": ", 1)[1] for loc in result.stats.skipped_locators]
    assert reasons[0] == "expected a JSON object"
    assert "tool_name" in reasons[1]
    assert "tool_input" in reasons[2]


def test_detect_and_registry() -> None:
    importer = ClaudeCodeHooksImporter()
    assert importer.detect((FIXTURES / "hooks.jsonl").read_bytes())
    assert importer.detect((FIXTURES / "hooks_no_ts.jsonl").read_bytes())
    assert not importer.detect((FIXTURES / "session.jsonl").read_bytes()[:8192])
    assert not importer.detect(b"")

    assert registry.detect(FIXTURES / "hooks.jsonl").name == "claude-code-hooks"
    assert registry.detect(FIXTURES / "session.jsonl").name == "claude-code"
    assert isinstance(registry.get("claude-code-hooks"), ClaudeCodeHooksImporter)
    with pytest.raises(TraceImportError, match="looks like claude-code traces"):
        registry.get_for(FIXTURES / "session.jsonl", "claude-code-hooks")
