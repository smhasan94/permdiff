from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from permdiff.cli.main import cli
from permdiff.importers.claude_code import ClaudeCodeHooksImporter
from permdiff.models.limits import MAX_LINE_BYTES

EVENT = {
    "session_id": "sess-0001",
    "transcript_path": "/home/dev/.claude/projects/-home-dev-project/sess-0001.jsonl",
    "cwd": "/home/dev/project",
    "permission_mode": "default",
    "hook_event_name": "PreToolUse",
    "tool_name": "Bash",
    "tool_input": {"command": "ls", "description": "List files"},
    "tool_use_id": "toolu_01",
}


def record(out: Path, stdin: str) -> tuple[int, str, str]:
    result = CliRunner().invoke(cli, ["record", "claude-code", "--out", str(out)], input=stdin)
    return result.exit_code, result.stdout, result.stderr


def test_valid_event_is_stamped_appended_and_round_trips(tmp_path: Path) -> None:
    out = tmp_path / "hooks.jsonl"

    code, stdout, stderr = record(out, json.dumps(EVENT))
    code2, _, _ = record(out, json.dumps({**EVENT, "tool_use_id": "toolu_02"}))

    assert (code, stdout, stderr) == (0, "", "")
    assert code2 == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["ts"].endswith("Z")
    assert {k: v for k, v in first.items() if k != "ts"} == EVENT

    imported = ClaudeCodeHooksImporter().read(out, strict=True)
    assert [c.id for c in imported.calls] == ["toolu_01", "toolu_02"]
    assert imported.calls[0].tool.name == "Bash"
    assert imported.calls[0].arguments == EVENT["tool_input"]
    assert imported.calls[0].context["cwd"] == "/home/dev/project"
    assert imported.calls[0].context["permission_mode"] == "default"


def test_other_hook_events_are_appended_and_skipped_by_the_importer(tmp_path: Path) -> None:
    out = tmp_path / "hooks.jsonl"

    code, stdout, _ = record(out, json.dumps({**EVENT, "hook_event_name": "PostToolUse"}))

    assert (code, stdout) == (0, "")
    assert json.loads(out.read_text())["hook_event_name"] == "PostToolUse"
    assert ClaudeCodeHooksImporter().read(out).stats.read == 0


@pytest.mark.parametrize(
    ("stdin", "reason"),
    [
        ("{not json", "invalid JSON"),
        ("", "empty stdin"),
        ("[1, 2]", "expected a JSON object"),
        (json.dumps({**EVENT, "pad": "x" * (MAX_LINE_BYTES + 1)}), "over the 1 MiB limit"),
    ],
)
def test_bad_input_exits_zero_silently_on_stdout_and_writes_nothing(
    tmp_path: Path, stdin: str, reason: str
) -> None:
    out = tmp_path / "hooks.jsonl"

    code, stdout, stderr = record(out, stdin)

    assert (code, stdout) == (0, "")
    assert stderr.startswith("permdiff record: ")
    assert reason in stderr
    assert stderr.count("\n") == 1
    assert not out.exists()


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="needs a non-root posix user")
def test_unwritable_output_exits_zero_with_one_stderr_line(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        code, stdout, stderr = record(locked / "hooks.jsonl", json.dumps(EVENT))
    finally:
        locked.chmod(0o700)

    assert (code, stdout) == (0, "")
    assert stderr.startswith("permdiff record: cannot write")
    assert stderr.count("\n") == 1


def test_default_out_is_under_the_claude_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    result = CliRunner().invoke(cli, ["record", "claude-code"], input=json.dumps(EVENT))

    assert result.exit_code == 0, result.output
    assert (tmp_path / ".claude" / "permdiff-hooks.jsonl").exists()
