"""``permdiff diff``: the core command (FR-27 initial surface)."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import click

from permdiff import _proc, api
from permdiff.cli._render import FORMATS, OutputOptions, emit_and_exit, parse_show_args
from permdiff.errors import ConfigError, ProcError
from permdiff.models.limits import DEFAULT_MAX_RECORDS
from permdiff.redact import RedactLevel
from permdiff.report import FailOn
from permdiff.report.grouping import (
    DEFAULT_GROUP_BY,
    DEFAULT_MAX_GROUPS,
    DEFAULT_SAMPLES,
    GROUP_FIELDS,
    validate_group_by,
)

DEFAULT_BASE = "origin/main"
DEFAULT_HEAD = "HEAD"
DEFAULT_POLICY = "policy"

F = TypeVar("F", bound=Callable[..., Any])


def output_flags(fn: F) -> F:
    """Options shared by ``diff`` and ``demo``; consumed via ``collect_output_options``."""
    decorators = (
        click.option("--format", "fmt_out", type=click.Choice(FORMATS), default="terminal"),
        click.option(
            "--fail-on",
            type=click.Choice([f.value for f in FailOn]),
            default=FailOn.WIDEN.value,
            show_default=True,
        ),
        click.option(
            "--redact",
            type=click.Choice([r.value for r in RedactLevel]),
            default=RedactLevel.SAFE.value,
            show_default=True,
        ),
        click.option("--show-args", default="", help="Comma-separated argument keys to reveal."),
        click.option("--samples", type=int, default=DEFAULT_SAMPLES, show_default=True),
        click.option(
            "--group-by",
            default=",".join(DEFAULT_GROUP_BY),
            show_default=True,
            help=f"Comma-separated fields: {', '.join(GROUP_FIELDS)}.",
        ),
        click.option("--max-groups", type=int, default=DEFAULT_MAX_GROUPS, show_default=True),
        click.option("--show-attribution", is_flag=True, help="Also list attribution changes."),
        click.option("--salt", "salt_hex", metavar="HEX", help="Fixed principal-hash salt."),
        click.option("--quiet", is_flag=True, help="Print only the summary block."),
        click.option("--no-color", is_flag=True, help="Disable ANSI colors."),
        click.option(
            "--output",
            type=click.Path(path_type=Path, dir_okay=False),
            default=None,
            help="Write the report to FILE instead of stdout.",
        ),
        click.option(
            "--pr-comment",
            is_flag=True,
            help="Markdown for a PR comment; refuses --redact none.",
        ),
        click.option(
            "--include-decisions",
            is_flag=True,
            help="JSON: include every call's base and head decision.",
        ),
    )
    for decorate in reversed(decorators):
        fn = decorate(fn)
    return fn


def collect_output_options(kwargs: dict[str, Any]) -> OutputOptions:
    """Pop the ``output_flags`` values out of a command's kwargs."""
    return OutputOptions(
        fmt=kwargs.pop("fmt_out"),
        fail_on=FailOn(kwargs.pop("fail_on")),
        redact=RedactLevel(kwargs.pop("redact")),
        show_args=parse_show_args(kwargs.pop("show_args")),
        samples=kwargs.pop("samples"),
        group_by=validate_group_by(kwargs.pop("group_by").split(",")),
        max_groups=kwargs.pop("max_groups"),
        show_attribution=kwargs.pop("show_attribution"),
        quiet=kwargs.pop("quiet"),
        no_color=kwargs.pop("no_color"),
        output=kwargs.pop("output"),
        pr_comment=kwargs.pop("pr_comment"),
        include_decisions=kwargs.pop("include_decisions"),
    ).validated()


ENGINE_OPTION_KEYS = ("decision", "opa_bin", "v0_compatible", "undefined", "nd_cache")


def engine_options(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Pop engine-specific flags; only the ones actually given are forwarded."""
    given = {key: kwargs.pop(key) for key in ENGINE_OPTION_KEYS}
    return {k: v for k, v in given.items() if v not in (None, False)}


def parse_salt(salt_hex: str | None) -> bytes | None:
    if salt_hex is None:
        return None
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError as exc:
        msg = f"--salt must be hex, got {salt_hex!r}"
        raise ConfigError(msg) from exc
    if not salt:
        msg = "--salt must not be empty"
        raise ConfigError(msg)
    return salt


def actor() -> str:
    """Who approved a widening: ``GITHUB_ACTOR``, else git's user.name, else ``unknown``."""
    if name := os.environ.get("GITHUB_ACTOR"):
        return name
    try:
        result = _proc.run(["git", "config", "user.name"])
    except ProcError:
        return "unknown"
    return result.stdout.strip() or "unknown"


@click.command("diff")
@click.option("--base", default=DEFAULT_BASE, show_default=True, help="Base git ref.")
@click.option("--head", default=DEFAULT_HEAD, show_default=True, help="Head git ref or WORKTREE.")
@click.option(
    "--policy", default=DEFAULT_POLICY, show_default=True, help="Policy path in the repo."
)
@click.option("--engine", required=True, help="Engine: python:module.path:callable (more later).")
@click.option(
    "--traces", "trace_patterns", multiple=True, required=True, help="Trace file or glob."
)
@click.option("--from", "fmt", default=api.AUTO_FORMAT, show_default=True, help="Importer name.")
@click.option("--repo", type=click.Path(path_type=Path), default=Path(), help="Repository root.")
@click.option("--strict", is_flag=True, help="Abort on the first malformed trace record.")
@click.option("--max-records", type=int, default=DEFAULT_MAX_RECORDS, show_default=True)
@click.option("--allow-widening", metavar="REASON", help="Exit 0 on widening; record REASON.")
@click.option("--verify-deterministic", is_flag=True, help="Evaluate twice; flag differences.")
@click.option("--decision", default=None, help="OPA rule path, e.g. data.agent.authz.decision.")
@click.option("--opa-bin", type=click.Path(path_type=Path), default=None, help="opa executable.")
@click.option("--v0-compatible", is_flag=True, help="Pass --v0-compatible to opa.")
@click.option(
    "--nd-cache",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Recorded nondeterministic builtin values (OPA nd_builtin_cache JSON).",
)
@click.option(
    "--undefined",
    type=click.Choice(["deny", "error"]),
    default=None,
    help="What an undefined OPA rule means. [default: deny]",
)
@output_flags
@click.pass_context
def diff_cmd(ctx: click.Context, /, **kwargs: Any) -> None:
    """Replay traces against the policy at two refs and report decision changes."""
    opts = collect_output_options(kwargs)
    salt = parse_salt(kwargs.pop("salt_hex"))
    allow_widening = kwargs.pop("allow_widening")
    imported = api.load_traces(
        kwargs.pop("trace_patterns"),
        fmt=kwargs.pop("fmt"),
        strict=kwargs.pop("strict"),
        max_records=kwargs.pop("max_records"),
    )
    report = api.diff(
        traces=imported.calls,
        salt=salt,
        keep_temp=bool(ctx.obj and ctx.obj.get("debug")),
        import_stats=imported.stats,
        allow_widening=(allow_widening, actor()) if allow_widening else None,
        engine_options=engine_options(kwargs),
        **kwargs,
    )
    emit_and_exit(ctx, report, opts)
