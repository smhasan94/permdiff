from __future__ import annotations

import json
from pathlib import Path

import pytest

from permdiff.errors import TraceImportError
from permdiff.importers import registry
from permdiff.importers.claude_code import FORMAT_TRANSCRIPT, ClaudeCodeImporter
from permdiff.models import Effect

FIXTURES = Path(__file__).parents[3] / "fixtures" / "claude_code"


def test_maps_tool_use_blocks_to_toolcalls() -> None:
    result = ClaudeCodeImporter().read(FIXTURES / "session.jsonl", strict=True)

    calls = {c.id: c for c in result.calls}
    assert result.stats.read == 7
    assert result.stats.skipped == 0
    assert list(calls) == [f"toolu_0{i}" for i in range(1, 8)]

    bash = calls["toolu_01"]
    assert bash.timestamp.isoformat() == "2026-09-25T08:48:25.277000+00:00"
    assert bash.tool.name == "Bash"
    assert bash.tool.server is None
    assert bash.arguments == {"command": "cd /home/dev/project && ls", "description": "List files"}
    assert bash.agent.id == "claude-code"
    assert bash.agent.version == "2.1.282"
    assert bash.resource.type == "shell"
    assert bash.context["session_id"] == "sess-0001"
    assert bash.context["cwd"] == "/home/dev/project"
    assert bash.context["git_branch"] == "main"
    assert bash.context["permission_mode"] == "default"
    assert bash.context["claude_code.version"] == "2.1.282"
    assert bash.context["claude_code.sidechain"] is False
    assert bash.context["claude_code.model_input_differs"] is True
    assert bash.recorded.effect == Effect.ALLOW
    assert bash.source is not None
    assert bash.source.format == FORMAT_TRANSCRIPT
    assert bash.source.locator.endswith("session.jsonl:4")

    read = calls["toolu_02"]
    assert read.resource.type == "file"
    assert read.resource.id == "/home/dev/project/README.md"
    assert "claude_code.model_input_differs" not in read.context

    write, grep = calls["toolu_03"], calls["toolu_04"]
    assert write.recorded.effect == Effect.DENY
    assert write.context["claude_code.denial_kind"] == "permission-rule"
    assert write.source is not None
    assert write.source.locator.endswith("session.jsonl:8")
    assert grep.recorded.effect == Effect.ALLOW
    assert grep.source is not None
    assert grep.source.locator.endswith("session.jsonl:8")

    rejected = calls["toolu_05"]
    assert rejected.recorded.effect == Effect.DENY
    assert rejected.context["claude_code.denial_kind"] == "user-rejected"
    assert rejected.context["permission_mode"] == "acceptEdits"

    mcp = calls["toolu_06"]
    assert mcp.tool.name == "mcp__github__create_issue"
    assert mcp.tool.server == "github"
    assert mcp.tool.type == "mcp"

    unfinished = calls["toolu_07"]
    assert unfinished.recorded.effect is None
    assert unfinished.resource.type == "url"
    assert unfinished.resource.id == "https://example.com/spec"


def test_principal_defaults_to_unknown_with_a_note(monkeypatch: pytest.MonkeyPatch) -> None:
    default = ClaudeCodeImporter().read(FIXTURES / "session.jsonl", strict=True)
    assert {c.principal.id for c in default.calls} == {"unknown"}
    assert all(c.context["claude_code.principal_missing"] is True for c in default.calls)

    monkeypatch.setenv("PERMDIFF_USER", "dev-user")
    via_env = ClaudeCodeImporter(principal_from="env:PERMDIFF_USER").read(
        FIXTURES / "session.jsonl"
    )
    assert {c.principal.id for c in via_env.calls} == {"dev-user"}
    assert all("claude_code.principal_missing" not in c.context for c in via_env.calls)

    via_key = ClaudeCodeImporter(principal_from="userType").read(FIXTURES / "session.jsonl")
    assert {c.principal.id for c in via_key.calls} == {"external"}


def test_subagent_transcript_marks_sidechain_and_agent_id() -> None:
    result = ClaudeCodeImporter().read(FIXTURES / "subagent.jsonl", strict=True)

    (call,) = result.calls
    assert call.context["claude_code.sidechain"] is True
    assert call.context["claude_code.agent_id"] == "a20ee8686ca95262a"
    assert call.recorded.effect == Effect.ALLOW
    assert "permission_mode" not in call.context


def test_invalid_lines_skip_and_count_or_abort_when_strict() -> None:
    lenient = ClaudeCodeImporter().read(FIXTURES / "invalid.jsonl")

    assert lenient.stats.read == 1
    assert lenient.calls[0].id == "toolu_ok"
    assert lenient.stats.skipped == 3
    reasons = [loc.split(": ", 1)[1] for loc in lenient.stats.skipped_locators]
    assert "tool_use block has no id" in reasons[0]
    assert "timestamp" in reasons[1]
    assert "invalid JSON" in reasons[2]

    with pytest.raises(TraceImportError, match=r"invalid\.jsonl:1"):
        ClaudeCodeImporter().read(FIXTURES / "invalid.jsonl", strict=True)


def test_oversized_line_is_skipped_and_counted(tmp_path: Path) -> None:
    line = {
        "type": "assistant",
        "sessionId": "s",
        "timestamp": "2026-09-25T08:50:00.000Z",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_big",
                    "name": "Write",
                    "input": {"file_path": "/p/big.txt", "content": "x" * (1 << 20)},
                }
            ],
        },
    }
    path = tmp_path / "big.jsonl"
    path.write_text(json.dumps(line) + "\n")

    result = ClaudeCodeImporter().read(path)

    assert result.stats.read == 0
    assert result.stats.skipped == 1
    assert "1 MiB limit" in result.stats.skipped_locators[0]


def test_detect_and_registry() -> None:
    importer = ClaudeCodeImporter()
    assert importer.detect((FIXTURES / "session.jsonl").read_bytes()[:8192])
    assert importer.detect((FIXTURES / "subagent.jsonl").read_bytes()[:8192])
    assert not importer.detect((FIXTURES / "hooks.jsonl").read_bytes()[:8192])
    assert not importer.detect(b'{"schema": "custody.trace.v1"}\n')
    assert not importer.detect(b"")

    assert registry.detect(FIXTURES / "session.jsonl").name == "claude-code"
    assert isinstance(registry.get("claude-code"), ClaudeCodeImporter)
    assert registry.get("claude-code", principal_from="env:USER").principal_from == "env:USER"  # type: ignore[attr-defined]
