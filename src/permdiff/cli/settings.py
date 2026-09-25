"""Shared selection and output flags for ``diff`` and ``check``, resolved through the config.

Every config-backed option defaults to ``None`` so "not given" is distinguishable; the
effective value comes from flags > environment > ``permdiff.toml`` > defaults.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import click

from permdiff import api
from permdiff.cli._render import FORMATS, OutputOptions, parse_show_args
from permdiff.config import Config, load_config
from permdiff.errors import ConfigError
from permdiff.importers.base import ImportResult
from permdiff.importers.filters import FilterResult, TraceFilters, apply_filters
from permdiff.redact import RedactLevel
from permdiff.report import FailOn
from permdiff.report.grouping import GROUP_FIELDS, validate_group_by

F = TypeVar("F", bound=Callable[..., Any])

# flag name -> (section, key)
CONFIG_FLAGS: dict[str, tuple[str, str]] = {
    "base": ("policy", "base"),
    "head": ("policy", "head"),
    "policy": ("policy", "path"),
    "engine": ("policy", "engine"),
    "trace_patterns": ("traces", "paths"),
    "fmt": ("traces", "format"),
    "strict": ("traces", "strict"),
    "max_records": ("traces", "max_records"),
    "since": ("traces", "since"),
    "until": ("traces", "until"),
    "principal_from": ("traces", "principal_from"),
    "decision": ("opa", "decision"),
    "v0_compatible": ("opa", "v0_compatible"),
    "undefined": ("opa", "undefined"),
    "nd_cache": ("opa", "nd_cache"),
    "fmt_out": ("report", "format"),
    "fail_on": ("report", "fail_on"),
    "redact": ("report", "redact"),
    "show_args": ("report", "show_args"),
    "samples": ("report", "samples"),
    "group_by": ("report", "group_by"),
    "max_groups": ("report", "max_groups"),
    "show_attribution": ("report", "show_attribution"),
}


def _apply(decorators: tuple[Callable[[F], F], ...], fn: F) -> F:
    for decorate in reversed(decorators):
        fn = decorate(fn)
    return fn


def selection_flags(fn: F) -> F:
    """Refs, policy, engine, traces, and engine options (all config-backed)."""
    return _apply(
        (
            click.option("--base", default=None, help="Base git ref. [config policy.base]"),
            click.option(
                "--head", default=None, help="Head git ref or WORKTREE. [config policy.head]"
            ),
            click.option(
                "--policy", default=None, help="Policy path in the repo. [config policy.path]"
            ),
            click.option(
                "--engine",
                default=None,
                help="opa | python:module:callable. [config policy.engine]",
            ),
            click.option(
                "--traces",
                "trace_patterns",
                multiple=True,
                help="Trace file or glob. [config traces.paths]",
            ),
            click.option(
                "--from", "fmt", default=None, help="Importer name or auto. [config traces.format]"
            ),
            click.option(
                "--repo", type=click.Path(path_type=Path), default=Path(), help="Repository root."
            ),
            click.option(
                "--strict", is_flag=True, default=None, help="Abort on the first malformed record."
            ),
            click.option(
                "--max-records",
                type=int,
                default=None,
                help="Record cap. [config traces.max_records]",
            ),
            click.option("--decision", default=None, help="OPA rule path. [config opa.decision]"),
            click.option(
                "--opa-bin", type=click.Path(path_type=Path), default=None, help="opa executable."
            ),
            click.option(
                "--v0-compatible", is_flag=True, default=None, help="Pass --v0-compatible to opa."
            ),
            click.option(
                "--undefined",
                type=click.Choice(["deny", "error"]),
                default=None,
                help="Undefined OPA rule meaning.",
            ),
            click.option(
                "--nd-cache",
                type=click.Path(path_type=Path, exists=True, dir_okay=False),
                default=None,
                help="Recorded nd_builtin_cache JSON.",
            ),
            click.option(
                "--since",
                default=None,
                help="Keep calls at or after 7d|12h|30m (from the newest trace) or an ISO time.",
            ),
            click.option("--until", default=None, help="Keep calls at or before an ISO time."),
            click.option(
                "--principal-from",
                default=None,
                help="OTel: attribute path for the principal, e.g. resource.attr.service.name.",
            ),
            click.option("--tool", "tool_globs", multiple=True, help="Keep tools matching GLOB."),
            click.option(
                "--agent", "agent_globs", multiple=True, help="Keep agents matching GLOB."
            ),
            click.option(
                "--principal",
                "principal_globs",
                multiple=True,
                help="Keep principals matching GLOB.",
            ),
        ),
        fn,
    )


def output_flags(fn: F) -> F:
    """Report shaping (config-backed) plus run-only switches."""
    return _apply(
        (
            click.option(
                "--format",
                "fmt_out",
                type=click.Choice(FORMATS),
                default=None,
                help="[config report.format]",
            ),
            click.option(
                "--fail-on",
                type=click.Choice([f.value for f in FailOn]),
                default=None,
                help="[config report.fail_on]",
            ),
            click.option(
                "--redact",
                type=click.Choice([r.value for r in RedactLevel]),
                default=None,
                help="[config report.redact]",
            ),
            click.option(
                "--show-args", default=None, help="Comma-separated argument keys to reveal."
            ),
            click.option(
                "--samples",
                type=int,
                default=None,
                help="Samples per group. [config report.samples]",
            ),
            click.option(
                "--group-by",
                default=None,
                help=f"Comma-separated fields: {', '.join(GROUP_FIELDS)}.",
            ),
            click.option("--max-groups", type=int, default=None, help="[config report.max_groups]"),
            click.option(
                "--show-attribution",
                is_flag=True,
                default=None,
                help="Also list attribution changes.",
            ),
            click.option("--salt", "salt_hex", metavar="HEX", help="Fixed principal-hash salt."),
            click.option("--quiet", is_flag=True, help="Print only the summary block."),
            click.option("--no-color", is_flag=True, help="Disable ANSI colors."),
            click.option(
                "--output",
                type=click.Path(path_type=Path, dir_okay=False),
                default=None,
                help="Write the report to FILE.",
            ),
            click.option(
                "--pr-comment",
                is_flag=True,
                help="Markdown for a PR comment; refuses --redact none.",
            ),
            click.option(
                "--include-decisions", is_flag=True, help="JSON: include every call's decisions."
            ),
        ),
        fn,
    )


def _split(value: str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    return tuple(v.strip() for v in value.split(",") if v.strip())


def overrides_from(kwargs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Pop config-backed flags from ``kwargs``; keep only the ones the user gave."""
    overrides: dict[str, dict[str, Any]] = {}
    for flag, (section, key) in CONFIG_FLAGS.items():
        if flag not in kwargs:
            continue
        value = kwargs.pop(flag)
        if value is None or value == ():
            continue
        if flag in ("show_args", "group_by"):
            value = _split(value)
        if flag == "nd_cache":
            value = str(value)
        overrides.setdefault(section, {})[key] = value
    return overrides


def resolve_config(ctx: click.Context, repo: Path, kwargs: dict[str, Any]) -> Config:
    explicit = ctx.obj.get("config") if ctx.obj else None
    start = Path.cwd()
    return load_config(
        start,
        env=os.environ,
        overrides=overrides_from(kwargs),
        explicit=explicit,
        stop_at=repo.resolve() if repo.exists() else None,
    )


def engine_options(config: Config) -> dict[str, Any]:
    """Engine-specific options for the resolved engine; only OPA takes any today."""
    if config.policy.engine != "opa":
        return {}
    opa = config.opa
    options: dict[str, Any] = {"decision": opa.decision, "undefined": opa.undefined}
    if opa.v0_compatible:
        options["v0_compatible"] = True
    if opa.nd_cache:
        options["nd_cache"] = Path(opa.nd_cache)
    if opa.capabilities not in ("", "default"):
        options["capabilities"] = Path(opa.capabilities)
    return options


def output_options(config: Config, kwargs: dict[str, Any]) -> OutputOptions:
    """Run-only switches come from ``kwargs``; shaping comes from the resolved config."""
    r = config.report
    return OutputOptions(
        fmt=r.format,
        fail_on=FailOn(r.fail_on),
        redact=RedactLevel(r.redact),
        show_args=parse_show_args(",".join(r.show_args)),
        samples=r.samples,
        group_by=validate_group_by(r.group_by),
        max_groups=r.max_groups,
        show_attribution=r.show_attribution,
        quiet=kwargs.pop("quiet"),
        no_color=kwargs.pop("no_color"),
        output=kwargs.pop("output"),
        pr_comment=kwargs.pop("pr_comment"),
        include_decisions=kwargs.pop("include_decisions"),
    ).validated()


def load_filtered_traces(
    config: Config, kwargs: dict[str, Any]
) -> tuple[ImportResult, FilterResult]:
    """Import per config, then apply the window from config and the glob flags (FR-6)."""
    filters = TraceFilters(
        since=config.traces.since,
        until=config.traces.until,
        tool=tuple(kwargs.pop("tool_globs")),
        agent=tuple(kwargs.pop("agent_globs")),
        principal=tuple(kwargs.pop("principal_globs")),
    )
    importer_options = (
        {"principal_from": config.traces.principal_from} if config.traces.principal_from else {}
    )
    imported = api.load_traces(
        require_traces(config),
        fmt=config.traces.format,
        strict=config.traces.strict,
        max_records=config.traces.max_records,
        importer_options=importer_options,
    )
    return imported, apply_filters(imported.calls, filters)


def require_traces(config: Config) -> tuple[str, ...]:
    if not config.traces.paths:
        msg = "no traces given: pass --traces FILE|GLOB or set [traces] paths in permdiff.toml"
        raise ConfigError(msg)
    return config.traces.paths
