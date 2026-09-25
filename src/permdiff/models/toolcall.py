"""Canonical decision input (overview §3.2)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, AwareDatetime, Field

from permdiff.models.base import Frozen
from permdiff.models.decision import Effect
from permdiff.models.limits import check_nesting

JsonObject = Annotated[Mapping[str, Any], AfterValidator(check_nesting)]
"""Opaque JSON object, nesting-limited. permdiff never interprets its contents."""


def _empty_object() -> dict[str, Any]:
    return {}


class Principal(Frozen):
    id: str
    type: str = "user"
    attrs: JsonObject = Field(default_factory=_empty_object)


class Agent(Frozen):
    id: str
    version: str | None = None
    attrs: JsonObject = Field(default_factory=_empty_object)


class Tool(Frozen):
    name: str
    server: str | None = None
    type: str | None = None


class Resource(Frozen):
    type: str | None = None
    id: str | None = None
    attrs: JsonObject = Field(default_factory=_empty_object)


class Recorded(Frozen):
    """What the runtime actually did, when the source knows. Never a decision input."""

    effect: Effect | None = None
    policy_hash: str | None = None


class Source(Frozen):
    format: str
    locator: str


class ToolCall(Frozen):
    """One recorded agent tool call. Every importer produces it; every evaluator consumes it."""

    id: str
    timestamp: AwareDatetime
    principal: Principal
    agent: Agent
    tool: Tool
    arguments: JsonObject | None = None
    resource: Resource = Field(default_factory=Resource)
    context: JsonObject = Field(default_factory=_empty_object)
    recorded: Recorded = Field(default_factory=Recorded)
    source: Source | None = None

    @staticmethod
    def derived_id(
        timestamp: datetime,
        principal_id: str,
        tool_name: str,
        arguments: Mapping[str, Any] | None,
    ) -> str:
        """SHA-256 hex over the canonical JSON of the identifying fields.

        Importers use this when the source has no stable id of its own.
        """
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            msg = "timestamp must be timezone-aware"
            raise ValueError(msg)
        payload = [timestamp.isoformat(), principal_id, tool_name, arguments]
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
