"""Claude Code example policy, head version: the change under review.

Compared with the base: destructive shell commands need approval, file writes outside the
session's working directory are denied, and ``WebFetch`` becomes allowed (a widening that
``permdiff diff`` flags).
"""

from __future__ import annotations

import re

from permdiff.demo.engine import Rule
from permdiff.models import ToolCall

DESTRUCTIVE_COMMAND = re.compile(
    r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\b|git\s+push\b.*(--force|-f)\b"
)


def _destructive(call: ToolCall) -> bool:
    command = (call.arguments or {}).get("command")
    return isinstance(command, str) and DESTRUCTIVE_COMMAND.search(command) is not None


def _outside_cwd(call: ToolCall) -> bool:
    cwd = call.context.get("cwd")
    path = (call.arguments or {}).get("file_path")
    if not isinstance(cwd, str) or not isinstance(path, str):
        return False
    return not path.startswith(cwd.rstrip("/") + "/")


DEFAULT = "deny"

RULES = (
    Rule(tool="Bash", effect="require_approval", when=_destructive, reason="destructive command"),
    Rule(tool="Bash", effect="allow"),
    Rule(tool="Read", effect="allow"),
    Rule(tool="Glob", effect="allow"),
    Rule(tool="Grep", effect="allow"),
    Rule(tool="Edit", effect="deny", when=_outside_cwd, reason="outside the working directory"),
    Rule(tool="Edit", effect="allow"),
    Rule(tool="Write", effect="deny", when=_outside_cwd, reason="outside the working directory"),
    Rule(tool="Write", effect="allow"),
    Rule(tool="WebFetch", effect="allow"),
)
