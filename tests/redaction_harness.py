"""Sentinel strings and the assertion every reporter test reuses (AC-17.4)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from permdiff.models import ToolCall

SENTINELS: dict[str, str] = {
    "principal_id": "sentinel-principal-9b1c@example.com",
    "principal_attr": "SENTINEL-PRINCIPAL-ATTR-4d2e",
    "agent_attr": "SENTINEL-AGENT-ATTR-8a71",
    "arg_top": "SENTINEL-ARG-TOP-7f3a",
    "arg_nested": "SENTINEL-ARG-NESTED-c05b",
    "arg_in_list": "SENTINEL-ARG-LIST-e9d4",
    "resource_id": "SENTINEL-RESOURCE-ID-1b6f",
    "resource_attr": "SENTINEL-RESOURCE-ATTR-33aa",
    "context": "SENTINEL-CONTEXT-CWD-5e77",
}
"""Unique strings that must never appear in ``safe`` output. Keys name where each is seeded."""


def sentinel_calls() -> tuple[ToolCall, ...]:
    """Two calls carrying every sentinel; tool and agent ids are deliberately plain."""
    base: dict[str, Any] = {
        "timestamp": datetime(2026, 9, 20, 14, 3, 11, tzinfo=UTC).isoformat(),
        "principal": {
            "id": SENTINELS["principal_id"],
            "attrs": {"department": SENTINELS["principal_attr"]},
        },
        "agent": {"id": "support-bot", "attrs": {"owner": SENTINELS["agent_attr"]}},
        "tool": {"name": "stripe.refund", "server": "stripe-mcp"},
        "arguments": {
            "charge_id": SENTINELS["arg_top"],
            "amount": 750,
            "meta": {"note": SENTINELS["arg_nested"], "tags": [SENTINELS["arg_in_list"], 1]},
        },
        "resource": {
            "type": "stripe.charge",
            "id": SENTINELS["resource_id"],
            "attrs": {"owner": SENTINELS["resource_attr"]},
        },
        "context": {"cwd": SENTINELS["context"], "env": "prod"},
    }
    return (
        ToolCall.model_validate({**base, "id": "sentinel-call-1"}),
        ToolCall.model_validate({**base, "id": "sentinel-call-2", "tool": {"name": "github.read"}}),
    )


def assert_no_sentinels(text: str, *, exclude: Iterable[str] = ()) -> None:
    """Fail if any sentinel (except the named keys) appears in ``text``."""
    skipped = set(exclude)
    leaked = [name for name, value in SENTINELS.items() if name not in skipped and value in text]
    assert not leaked, f"redaction leaked {leaked}"
