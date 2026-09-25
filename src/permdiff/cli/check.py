"""``permdiff check``: validate traces and compile both refs without diffing (FR-25)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from permdiff.cli.settings import (
    engine_options,
    load_filtered_traces,
    resolve_config,
    selection_flags,
)
from permdiff.errors import EXIT_OK, EXIT_TOOL_ERROR
from permdiff.evaluators import registry
from permdiff.policy import source_for


@click.command("check")
@selection_flags
@click.pass_context
def check_cmd(ctx: click.Context, /, **kwargs: Any) -> None:
    """Parse the traces and compile the policy at both refs; exit 1 on any failure."""
    repo: Path = kwargs.pop("repo")
    opa_bin: Path | None = kwargs.pop("opa_bin")
    config = resolve_config(ctx, repo, kwargs)
    imported, selected = load_filtered_traces(config, kwargs)
    click.echo(
        f"traces: {imported.stats.read:,} calls ({imported.stats.skipped:,} skipped, "
        f"{selected.filtered:,} filtered out)"
    )
    options = engine_options(config)
    if opa_bin is not None:
        options["opa_bin"] = opa_bin
    evaluator = registry.resolve(config.policy.engine, **options)
    failed = False
    for ref in (config.policy.base, config.policy.head):
        with source_for(repo, ref, config.policy.path).materialize() as materialized:
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
