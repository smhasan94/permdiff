"""``permdiff.toml`` sections (FR-23). Every key has a default; unknown keys are errors."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from permdiff.models import Frozen
from permdiff.models.limits import DEFAULT_MAX_RECORDS

CONFIG_FILENAME = "permdiff.toml"
ENV_PREFIX = "PERMDIFF"


class PolicyConfig(Frozen):
    engine: str = "opa"
    path: str = "policy"
    base: str = "origin/main"
    head: str = "HEAD"


class OpaConfig(Frozen):
    decision: str = "data.agent.authz.decision"
    capabilities: str = "default"
    """``default`` (restricted, no network) or a capabilities file path."""
    nd_cache: str = ""
    version: str = "1.21.0"
    undefined: Literal["deny", "error"] = "deny"
    v0_compatible: bool = False


class CedarConfig(Frozen):
    principal: str = 'User::"{principal.id}"'
    action: str = 'Action::"{tool.name}"'
    resource: str = 'Resource::"{resource.id}"'
    approval_annotation: str = "require_approval"


class TracesConfig(Frozen):
    paths: tuple[str, ...] = ()
    format: str = "auto"
    since: str | None = None
    until: str | None = None
    strict: bool = False
    max_records: int = DEFAULT_MAX_RECORDS
    principal_from: str | None = None
    """OTel: attribute path for the principal, e.g. ``resource.attr.service.name``."""
    input_map: tuple[str, ...] = ()
    """OPA decision logs: ``target=source`` pairs building a ToolCall from a foreign input."""


class ReportConfig(Frozen):
    format: Literal["terminal", "markdown", "json", "sarif"] = "terminal"
    redact: Literal["safe", "none"] = "safe"
    show_args: tuple[str, ...] = ()
    samples: int = 3
    group_by: tuple[str, ...] = ("tool",)
    fail_on: Literal["widen", "any-change", "cant-evaluate", "none"] = "widen"
    max_groups: int = 50
    show_attribution: bool = False


class Config(Frozen):
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    opa: OpaConfig = Field(default_factory=OpaConfig)
    cedar: CedarConfig = Field(default_factory=CedarConfig)
    traces: TracesConfig = Field(default_factory=TracesConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
