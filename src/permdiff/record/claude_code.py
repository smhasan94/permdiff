"""Claude Code ``PreToolUse`` recorder helpers.

The hook command (``permdiff record claude-code``) stamps the stdin object with ``ts`` and
appends it to a JSONL file that ``--from claude-code-hooks`` reads. Everything here is a
pure function or a single filesystem call so the command itself can stay tiny and never
fail loudly: Claude Code parses a hook's stdout and treats exit code 2 as a block.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from permdiff.errors import ConfigError

DEFAULT_OUT = Path("~/.claude/permdiff-hooks.jsonl")
DEFAULT_SETTINGS = Path("~/.claude/settings.json")
HOOK_COMMAND = "permdiff record claude-code"
TIMESTAMP_KEY = "ts"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
"""Same shape ``jq``'s ``now | todate`` produces, so both hook variants import alike."""
NEW_FILE_MODE = 0o600


def stamp(event: Mapping[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """A copy of ``event`` with ``ts`` set to ``now`` (UTC, seconds) unless already present."""
    if event.get(TIMESTAMP_KEY) not in (None, ""):
        return dict(event)
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    return {**event, TIMESTAMP_KEY: moment.strftime(TIMESTAMP_FORMAT)}


def append_line(path: Path, record: Mapping[str, Any]) -> None:
    """Append one JSON line; creates parents and, for a new file, owner-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, NEW_FILE_MODE)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fh.write(line)


HOOK_TIMEOUT_SECONDS = 5
PRE_TOOL_USE = "PreToolUse"
_INSTALLED_MARKER = "record claude-code"


def hook_entry(out: Path, executable: str = HOOK_COMMAND) -> dict[str, Any]:
    """The ``settings.json`` ``PreToolUse`` entry that runs the recorder for every tool."""
    prefix = HOOK_COMMAND if executable == HOOK_COMMAND else f"{executable} record claude-code"
    command = f"{prefix} --out {shlex.quote(str(out))}"
    return {
        "matcher": "",
        "hooks": [{"type": "command", "command": command, "timeout": HOOK_TIMEOUT_SECONDS}],
    }


def _pre_tool_use_entries(settings: Mapping[str, Any]) -> list[Any]:
    hooks = settings.get("hooks")
    if not isinstance(hooks, Mapping):
        return []
    entries = hooks.get(PRE_TOOL_USE)
    return list(entries) if isinstance(entries, list) else []


def is_installed(settings: Mapping[str, Any]) -> bool:
    """Whether any ``PreToolUse`` hook already runs the recorder (any path, any binary)."""
    for entry in _pre_tool_use_entries(settings):
        if not isinstance(entry, Mapping) or not isinstance(entry.get("hooks"), list):
            continue
        for hook in entry["hooks"]:
            if isinstance(hook, Mapping) and _INSTALLED_MARKER in str(hook.get("command", "")):
                return True
    return False


def merge_hook(settings: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]:
    """A new settings document with ``entry`` appended to ``hooks.PreToolUse``."""
    hooks = settings.get("hooks")
    hooks_copy: dict[str, Any] = dict(hooks) if isinstance(hooks, Mapping) else {}
    hooks_copy[PRE_TOOL_USE] = [*_pre_tool_use_entries(settings), dict(entry)]
    return {**settings, "hooks": hooks_copy}


def load_settings(path: Path) -> dict[str, Any]:
    """``{}`` when the file is absent; ``ConfigError`` when it is not a JSON object."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        msg = f"cannot read {path}: {exc.strerror or exc}"
        raise ConfigError(msg) from exc
    try:
        document = json.loads(text)
    except ValueError as exc:
        msg = f"cannot parse {path}: {exc}"
        raise ConfigError(msg) from exc
    if not isinstance(document, dict):
        msg = f"cannot use {path}: expected a JSON object at the top level"
        raise ConfigError(msg)
    return document


def write_settings(path: Path, document: Mapping[str, Any]) -> Path | None:
    """Write pretty JSON; back up an existing file to ``<name>.bak`` first. Returns the backup."""
    backup: Path | None = None
    if path.exists():
        backup = path.with_name(path.name + ".bak")
        shutil.copyfile(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return backup
