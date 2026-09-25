"""``permdiff check``: validate traces and compile both refs without diffing (FR-25)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from permdiff import api
from permdiff.cli.diff import DEFAULT_BASE, DEFAULT_HEAD, DEFAULT_POLICY, engine_options
from permdiff.errors import EXIT_OK, EXIT_TOOL_ERROR
from permdiff.evaluators import registry
from permdiff.models.limits import DEFAULT_MAX_RECORDS
from permdiff.policy import source_for


@click.command("check")
@click.option("--base", default=DEFAULT_BASE, show_default=True, help="Base git ref.")
@click.option("--head", default=DEFAULT_HEAD, show_default=True, help="Head git ref or WORKTREE.")
@click.option(
    "--policy", default=DEFAULT_POLICY, show_default=True, help="Policy path in the repo."
)
@click.option("--engine", required=True, help="Engine: opa or python:module.path:callable.")
@click.option(
    "--traces", "trace_patterns", multiple=True, required=True, help="Trace file or glob."
)
@click.option("--from", "fmt", default=api.AUTO_FORMAT, show_default=True, help="Importer name.")
@click.option("--repo", type=click.Path(path_type=Path), default=Path(), help="Repository root.")
@click.option("--strict", is_flag=True, help="Abort on the first malformed trace record.")
@click.option("--max-records", type=int, default=DEFAULT_MAX_RECORDS, show_default=True)
@click.option("--decision", default=None, help="OPA rule path, e.g. data.agent.authz.decision.")
@click.option("--opa-bin", type=click.Path(path_type=Path), default=None, help="opa executable.")
@click.option("--v0-compatible", is_flag=True, help="Pass --v0-compatible to opa.")
@click.option("--undefined", type=click.Choice(["deny", "error"]), default=None)
@click.option(
    "--nd-cache", type=click.Path(path_type=Path, exists=True, dir_okay=False), default=None
)
@click.pass_context
def check_cmd(ctx: click.Context, /, **kwargs: Any) -> None:
    """Parse the traces and compile the policy at both refs; exit 1 on any failure."""
    options = engine_options(kwargs)
    imported = api.load_traces(
        kwargs.pop("trace_patterns"),
        fmt=kwargs.pop("fmt"),
        strict=kwargs.pop("strict"),
        max_records=kwargs.pop("max_records"),
    )
    click.echo(f"traces: {imported.stats.read:,} calls ({imported.stats.skipped:,} skipped)")
    evaluator = registry.resolve(kwargs.pop("engine"), **options)
    repo, policy = kwargs.pop("repo"), kwargs.pop("policy")
    failed = False
    for ref in (kwargs.pop("base"), kwargs.pop("head")):
        with source_for(repo, ref, policy).materialize() as materialized:
            prepared = evaluator.prepare(materialized.path, label=materialized.label)
            error = getattr(prepared, "compile_error", None)
            prepared.close()
        sha = f" ({materialized.sha[:12]})" if materialized.sha else ""
        if error:
            failed = True
            click.echo(f"{materialized.label}{sha}: FAIL {error}")
        else:
            click.echo(f"{materialized.label}{sha}: ok")
    ctx.exit(EXIT_TOOL_ERROR if failed else EXIT_OK)
