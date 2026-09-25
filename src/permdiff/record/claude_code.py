"""Claude Code ``PreToolUse`` recorder helpers.

The hook command (``permdiff record claude-code``) stamps the stdin object with ``ts`` and
appends it to a JSONL file that ``--from claude-code-hooks`` reads. Everything here is a
pure function or a single filesystem call so the command itself can stay tiny and never
fail loudly: Claude Code parses a hook's stdout and treats exit code 2 as a block.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
