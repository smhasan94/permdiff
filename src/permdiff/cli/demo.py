"""``permdiff demo``: run the bundled example offline (FR-24)."""

from __future__ import annotations

from typing import Any

import click

from permdiff import api, demo
from permdiff.cli._render import OutputOptions, emit_and_exit, parse_show_args
from permdiff.cli.diff import parse_salt
from permdiff.cli.settings import output_flags
from permdiff.config.model import ReportConfig
from permdiff.errors import EngineError
from permdiff.policy import DirectorySource
from permdiff.redact import RedactLevel
from permdiff.report import FailOn
from permdiff.report.grouping import validate_group_by

ENGINES = ("auto", "opa", "python", "cedar")
FALLBACK_NOTE = (
    "note: opa is not installed, using the Python engine; run `permdiff setup opa` "
    "then `permdiff demo --engine opa` for the Rego version"
)


def demo_output_options(kwargs: dict[str, Any]) -> OutputOptions:
    """Shaping flags with the config defaults; the demo reads no permdiff.toml."""
    defaults = ReportConfig()

    def pick(flag: str, default: Any) -> Any:
        value = kwargs.pop(flag)
        return default if value is None else value

    return OutputOptions(
        fmt=pick("fmt_out", defaults.format),
        fail_on=FailOn(pick("fail_on", defaults.fail_on)),
        redact=RedactLevel(pick("redact", defaults.redact)),
        show_args=parse_show_args(pick("show_args", "")),
        samples=pick("samples", defaults.samples),
        group_by=validate_group_by(pick("group_by", ",".join(defaults.group_by)).split(",")),
        max_groups=pick("max_groups", defaults.max_groups),
        show_attribution=bool(pick("show_attribution", defaults.show_attribution)),
        quiet=kwargs.pop("quiet"),
        no_color=kwargs.pop("no_color"),
        output=kwargs.pop("output"),
        pr_comment=kwargs.pop("pr_comment"),
        include_decisions=kwargs.pop("include_decisions"),
    ).validated()


def choose_engine(requested: str) -> tuple[str, dict[str, Any]]:
    """``auto`` picks OPA when the pinned binary is already present, else Python."""
    from permdiff.evaluators.opa.binary import resolve_binary  # noqa: PLC0415  # keep start fast

    if requested == "python":
        return demo.ENGINE_SPEC, {}
    if requested == "cedar":
        return "cedar", {"resource": demo.CEDAR_RESOURCE}
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
    opts = demo_output_options(kwargs)
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
