"""Claude Code example policy, base version: what is in force today.

Rule table for the bundled ``python:permdiff.demo.engine:evaluate`` engine. Tool names are
Claude Code's (``Bash``, ``Read``, ``mcp__<server>__<tool>``); the first matching rule wins.
"""

from __future__ import annotations

from permdiff.demo.engine import Rule

DEFAULT = "deny"

RULES = (
    Rule(tool="Bash", effect="allow"),
    Rule(tool="Read", effect="allow"),
    Rule(tool="Glob", effect="allow"),
    Rule(tool="Grep", effect="allow"),
    Rule(tool="Edit", effect="allow"),
    Rule(tool="Write", effect="allow"),
)
