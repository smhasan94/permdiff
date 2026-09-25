from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from permdiff.errors import ConfigError
from permdiff.record.claude_code import (
    TIMESTAMP_KEY,
    append_line,
    hook_entry,
    is_installed,
    load_settings,
    merge_hook,
    stamp,
)

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


def test_hook_entry_quotes_the_output_path() -> None:
    entry = hook_entry(Path("/home/dev/my logs/hooks.jsonl"), executable="/opt/bin/permdiff")

    assert entry["matcher"] == ""
    (hook,) = entry["hooks"]
    assert hook["type"] == "command"
    assert (
        hook["command"]
        == "/opt/bin/permdiff record claude-code --out '/home/dev/my logs/hooks.jsonl'"
    )
    assert hook["timeout"] == 5


def test_merge_hook_appends_and_leaves_the_input_alone() -> None:
    entry = hook_entry(Path("/home/dev/h.jsonl"))
    existing = {
        "model": "opus",
        "hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}]
        },
    }
    snapshot = json.dumps(existing, sort_keys=True)

    merged = merge_hook(existing, entry)

    assert json.dumps(existing, sort_keys=True) == snapshot
    assert merged["model"] == "opus"
    assert merged["hooks"]["PreToolUse"][0]["matcher"] == "Bash"
    assert merged["hooks"]["PreToolUse"][1] == entry
    assert not is_installed(existing)
    assert is_installed(merged)
    assert merge_hook({}, entry) == {"hooks": {"PreToolUse": [entry]}}


def test_is_installed_ignores_malformed_hook_sections() -> None:
    assert not is_installed({"hooks": "nope"})
    assert not is_installed({"hooks": {"PreToolUse": [None, {"hooks": "x"}, {"hooks": [{}]}]}})


def test_load_settings_reads_missing_as_empty_and_rejects_bad_json(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "absent.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{oops")
    with pytest.raises(ConfigError, match=r"bad\.json"):
        load_settings(bad)
    array = tmp_path / "array.json"
    array.write_text("[]")
    with pytest.raises(ConfigError, match="object"):
        load_settings(array)
