"""Fixture callables for the Python evaluator. Each has signature (call, policy_dir)."""

from __future__ import annotations

import itertools
import json
from datetime import UTC
from pathlib import Path
from typing import Any

from permdiff.models import Decision, Effect, ToolCall

_counter = itertools.count()
NOT_ALLOWED = "not_allowed_here"


def allow_all(call: ToolCall, policy_dir: Path) -> str:
    return "allow"


def by_table(call: ToolCall, policy_dir: Path) -> str:
    """Effect from ``<policy_dir>/rules.json`` keyed by tool name; default deny."""
    table: dict[str, str] = json.loads((policy_dir / "rules.json").read_text(encoding="utf-8"))
    return table.get(call.tool.name, "deny")


def returns_decision(call: ToolCall, policy_dir: Path) -> Decision:
    return Decision(
        call_id="wrong-id",
        effect=Effect.REQUIRE_APPROVAL,
        reasons=("amount over limit",),
        determining=("rules.py:returns_decision",),
        engine="whatever",
    )


def raises_for_tool(call: ToolCall, policy_dir: Path) -> str:
    if call.tool.name == "boom":
        msg = f"cannot evaluate {call.tool.name}"
        raise RuntimeError(msg)
    return "allow"


def returns_garbage(call: ToolCall, policy_dir: Path) -> Any:
    return 42


def flip_flop(call: ToolCall, policy_dir: Path) -> str:
    """Deliberately nondeterministic: alternates on every invocation."""
    return "allow" if next(_counter) % 2 == 0 else "deny"


def business_hours(call: ToolCall, policy_dir: Path) -> str:
    """Time-dependent on the trace clock only: allow 09:00-17:00 UTC."""
    hour = call.timestamp.astimezone(UTC).hour
    return "allow" if 9 <= hour < 17 else "require_approval"


not_callable = "I am a string"
