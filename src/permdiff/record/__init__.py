"""Trace recording helpers (FR-L11): a thin Claude Code hook, not a store."""

from __future__ import annotations

from permdiff.record.claude_code import (
    DEFAULT_OUT,
    DEFAULT_SETTINGS,
    HOOK_COMMAND,
    append_line,
    hook_entry,
    is_installed,
    load_settings,
    merge_hook,
    stamp,
    write_settings,
)

__all__ = [
    "DEFAULT_OUT",
    "DEFAULT_SETTINGS",
    "HOOK_COMMAND",
    "append_line",
    "hook_entry",
    "is_installed",
    "load_settings",
    "merge_hook",
    "stamp",
    "write_settings",
]
