"""``permdiff diff``: the core command (FR-27 initial surface)."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import click

from permdiff import api
from permdiff.errors import ConfigError
from permdiff.models.limits import DEFAULT_MAX_RECORDS
from permdiff.redact import RedactLevel, Redactor
from permdiff.report import FailOn, gate, render_terminal
from permdiff.report.grouping import DEFAULT_SAMPLES

FORMATS = ("terminal",)
DEFAULT_BASE = "origin/main"
DEFAULT_HEAD = "HEAD"
DEFAULT_POLICY = "policy"


@dataclass(frozen=True)
class RenderOptions:
    fail_on: FailOn
    quiet: bool
    color: bool
    samples: int


def _actor() -> str:
    """Who approved a widening: ``GITHUB_ACTOR``, else git's user.name, else ``unknown``."""
    if actor := os.environ.get("GITHUB_ACTOR"):
        return actor
    try:
        completed = subprocess.run(
            ["git", "config", "user.name"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _parse_salt(salt_hex: str | None) -> bytes | None:
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


def _use_color(no_color: bool) -> bool:
    return not no_color and not os.environ.get("NO_COLOR") and sys.stdout.isatty()


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
@click.option("--format", "fmt_out", type=click.Choice(FORMATS), default="terminal")
@click.option(
    "--fail-on",
    type=click.Choice([f.value for f in FailOn]),
    default=FailOn.WIDEN.value,
    show_default=True,
)
@click.option("--allow-widening", metavar="REASON", help="Exit 0 on widening; record REASON.")
@click.option(
    "--redact",
    type=click.Choice([r.value for r in RedactLevel]),
    default=RedactLevel.SAFE.value,
    show_default=True,
)
@click.option("--show-args", default="", help="Comma-separated argument keys to reveal.")
@click.option("--samples", type=int, default=DEFAULT_SAMPLES, show_default=True)
@click.option("--salt", "salt_hex", metavar="HEX", help="Fixed principal-hash salt.")
@click.option("--verify-deterministic", is_flag=True, help="Evaluate twice; flag differences.")
@click.option("--quiet", is_flag=True, help="Print only the summary block.")
@click.option("--no-color", is_flag=True, help="Disable ANSI colors.")
@click.pass_context
def diff_cmd(
    ctx: click.Context,
    base: str,
    head: str,
    policy: str,
    engine: str,
    trace_patterns: tuple[str, ...],
    fmt: str,
    repo: Path,
    strict: bool,
    max_records: int,
    fmt_out: str,
    fail_on: str,
    allow_widening: str | None,
    redact: str,
    show_args: str,
    samples: int,
    salt_hex: str | None,
    verify_deterministic: bool,
    quiet: bool,
    no_color: bool,
) -> None:
    """Replay traces against the policy at two refs and report decision changes."""
    salt = _parse_salt(salt_hex)
    imported = api.load_traces(trace_patterns, fmt=fmt, strict=strict, max_records=max_records)
    report = api.diff(
        traces=imported.calls,
        base=base,
        head=head,
        policy=policy,
        engine=engine,
        repo=repo,
        salt=salt,
        verify_deterministic=verify_deterministic,
        keep_temp=bool(ctx.obj and ctx.obj.get("debug")),
        import_stats=imported.stats,
        allow_widening=(allow_widening, _actor()) if allow_widening else None,
    )
    redactor = Redactor(
        level=RedactLevel(redact),
        salt=bytes.fromhex(report.header.salt),
        show_args=frozenset(k.strip() for k in show_args.split(",") if k.strip()),
        show_principal=True,
    )
    exit_code = gate(report, FailOn(fail_on))
    text = render_terminal(
        redactor.report(report),
        exit_code=exit_code,
        fail_on=FailOn(fail_on),
        quiet=quiet,
        color=_use_color(no_color),
        samples=samples,
    )
    click.echo(text, nl=False)
    ctx.exit(exit_code)
