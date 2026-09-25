from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from permdiff.record.claude_code import TIMESTAMP_KEY, append_line, stamp

NOW = datetime(2026, 9, 25, 8, 48, 25, 500_000, tzinfo=UTC)


def test_stamp_adds_ts_without_touching_the_input() -> None:
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash"}

    stamped = stamp(event, now=NOW)

    assert stamped == {**event, TIMESTAMP_KEY: "2026-09-25T08:48:25Z"}
    assert TIMESTAMP_KEY not in event


def test_stamp_keeps_an_existing_ts() -> None:
    event = {"hook_event_name": "PreToolUse", TIMESTAMP_KEY: "2020-01-01T00:00:00Z"}

    assert stamp(event, now=NOW)[TIMESTAMP_KEY] == "2020-01-01T00:00:00Z"


def test_stamp_defaults_to_utc_now() -> None:
    before = datetime.now(UTC).replace(microsecond=0)
    ts = stamp({})[TIMESTAMP_KEY]
    parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert before <= parsed <= datetime.now(UTC)


def test_append_line_creates_parents_with_owner_only_mode_and_appends(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "hooks.jsonl"

    append_line(path, {"a": 1})
    append_line(path, {"b": "two"})

    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [{"a": 1}, {"b": "two"}]
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_append_line_keeps_an_existing_file_mode(tmp_path: Path) -> None:
    path = tmp_path / "hooks.jsonl"
    path.write_text("")
    path.chmod(0o644)

    append_line(path, {"a": 1})

    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_append_line_propagates_os_errors(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("")

    with pytest.raises(OSError, match="file"):
        append_line(blocker / "hooks.jsonl", {"a": 1})
