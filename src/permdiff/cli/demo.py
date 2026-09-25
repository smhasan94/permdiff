"""``permdiff demo``: run the bundled example offline (FR-24)."""

from __future__ import annotations

import logging
from typing import Any

import click

from permdiff import api, demo
from permdiff.cli._render import emit_and_exit
from permdiff.cli.diff import collect_output_options, output_flags, parse_salt
from permdiff.errors import EngineError
from permdiff.policy import DirectorySource

log = logging.getLogger(__name__)

ENGINES = ("auto", "opa", "python")
FALLBACK_NOTE = (
    "note: opa is not installed, using the Python engine; run `permdiff setup opa` "
    "then `permdiff demo --engine opa` for the Rego version"
)


def choose_engine(requested: str) -> tuple[str, dict[str, Any]]:
    """``auto`` picks OPA when the pinned binary is already present, else Python."""
    from permdiff.evaluators.opa.binary import resolve_binary  # noqa: PLC0415  # keep start fast

    if requested == "python":
        return demo.ENGINE_SPEC, {}
    try:
        opa_bin = resolve_binary(download_missing=(requested == "opa"))
    except EngineError:
        if requested == "opa":
            raise
        click.echo(FALLBACK_NOTE, err=True)
        return demo.ENGINE_SPEC, {}
    return "opa", {"decision": demo.OPA_DECISION, "opa_bin": opa_bin}


@click.command("demo")
@click.option("--engine", type=click.Choice(ENGINES), default="auto", show_default=True)
@output_flags
@click.pass_context
def demo_cmd(ctx: click.Context, /, **kwargs: Any) -> None:
    """Diff two bundled policy versions over a 200-call synthetic corpus. Needs nothing else."""
    opts = collect_output_options(kwargs)
    salt = parse_salt(kwargs.pop("salt_hex"))
    engine, engine_options = choose_engine(kwargs.pop("engine"))
    imported = api.load_traces([demo.CORPUS], fmt="jsonl")
    report = api.diff_sources(
        traces=imported.calls,
        base=DirectorySource(demo.POLICY_BASE, demo.BASE_LABEL),
        head=DirectorySource(demo.POLICY_HEAD, demo.HEAD_LABEL),
        policy_path="demo/policy",
        engine=engine,
        engine_options=engine_options,
        salt=salt,
        import_stats=imported.stats,
    )
    emit_and_exit(ctx, report, opts)
