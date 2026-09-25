"""``permdiff demo``: run the bundled example offline (FR-24)."""

from __future__ import annotations

from typing import Any

import click

from permdiff import api, demo
from permdiff.cli._render import emit_and_exit
from permdiff.cli.diff import collect_output_options, output_flags, parse_salt
from permdiff.policy import DirectorySource

ENGINES = ("python",)


@click.command("demo")
@click.option("--engine", type=click.Choice(ENGINES), default="python", show_default=True)
@output_flags
@click.pass_context
def demo_cmd(ctx: click.Context, /, **kwargs: Any) -> None:
    """Diff two bundled policy versions over a 200-call synthetic corpus. Needs nothing else."""
    opts = collect_output_options(kwargs)
    salt = parse_salt(kwargs.pop("salt_hex"))
    kwargs.pop("engine")  # only "python" for now; OPA arrives with E2
    imported = api.load_traces([demo.CORPUS], fmt="jsonl")
    report = api.diff_sources(
        traces=imported.calls,
        base=DirectorySource(demo.POLICY_BASE, demo.BASE_LABEL),
        head=DirectorySource(demo.POLICY_HEAD, demo.HEAD_LABEL),
        policy_path="demo/policy",
        engine=demo.ENGINE_SPEC,
        salt=salt,
        import_stats=imported.stats,
    )
    emit_and_exit(ctx, report, opts)
