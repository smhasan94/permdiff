"""``permdiff convert``: write any supported trace format as canonical permdiff JSONL (FR-7)."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import click

from permdiff import api
from permdiff.errors import TraceImportError
from permdiff.evaluators.opa.ndcache import (
    ND_CACHE_CONTEXT_KEY,
    merge_nd_caches,
    render_nd_cache_file,
)
from permdiff.importers.input_map import parse_input_map
from permdiff.importers.jsonl import FORMAT_NAME
from permdiff.models import Source, ToolCall
from permdiff.models.limits import DEFAULT_MAX_RECORDS


def to_jsonl_line(call: ToolCall) -> str:
    """Canonical JSONL: the record keeps its original source so provenance survives."""
    source = call.source or Source(format=FORMAT_NAME, locator="")
    return call.model_copy(update={"source": source}).model_dump_json(exclude_none=False) + "\n"


@click.command("convert")
@click.argument("files", nargs=-1, required=True)
@click.option("--from", "fmt", default=api.AUTO_FORMAT, show_default=True, help="Importer name.")
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Output JSONL (default stdout).",
)
@click.option("--strict", is_flag=True, help="Abort on the first malformed record.")
@click.option(
    "--nd-cache-out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Merge the OPA decision-log events' nd_builtin_cache into this file (for --nd-cache).",
)
@click.option("--max-records", type=int, default=DEFAULT_MAX_RECORDS, show_default=True)
@click.option(
    "--principal-from",
    default=None,
    help="Principal source: OTel attribute path, or env:VAR / a top-level key for Claude Code.",
)
@click.option(
    "--input-map",
    "input_map",
    multiple=True,
    help="OPA decision logs: target=source pair(s) for a foreign input shape.",
)
@click.option("--decision", default=None, help="OPA decision logs: rule path for package results.")
def convert_cmd(
    files: tuple[str, ...],
    fmt: str,
    output: Path | None,
    strict: bool,
    nd_cache_out: Path | None,
    max_records: int,
    principal_from: str | None,
    input_map: tuple[str, ...],
    decision: str | None,
) -> None:
    """Convert any supported trace format to permdiff JSONL."""
    options: dict[str, object] = {}
    if principal_from:
        options["principal_from"] = principal_from
    if input_map:
        options["input_map"] = parse_input_map(input_map)
    if decision:
        options["decision"] = decision
    result = api.load_traces(
        files, fmt=fmt, strict=strict, max_records=max_records, importer_options=options
    )
    text = "".join(to_jsonl_line(c) for c in result.calls)
    if output is not None:
        try:
            output.write_text(text, encoding="utf-8")
        except OSError as exc:
            msg = f"cannot write {output}: {exc.strerror or exc}"
            raise TraceImportError(msg) from exc
    else:
        sys.stdout.write(text)
    click.echo(
        f"converted {result.stats.read:,} calls ({result.stats.skipped:,} skipped)"
        + (f" to {output}" if output is not None else ""),
        err=True,
    )
    if nd_cache_out is not None:
        _write_nd_cache(result.calls, nd_cache_out, strict=strict)


def _write_nd_cache(calls: Sequence[ToolCall], target: Path, *, strict: bool) -> None:
    cache, conflicts = merge_nd_caches(calls)
    for conflict in conflicts:
        click.echo(
            f"nd_builtin_cache conflict: {conflict.builtin} {conflict.args}: kept "
            f"{json.dumps(conflict.kept)} from {conflict.kept_from}, dropped "
            f"{json.dumps(conflict.dropped)} from {conflict.dropped_from}",
            err=True,
        )
    if conflicts and strict:
        msg = f"--nd-cache-out: {len(conflicts)} conflicting recorded value(s); nothing written"
        raise TraceImportError(msg)
    try:
        target.write_text(render_nd_cache_file(cache), encoding="utf-8")
    except OSError as exc:
        msg = f"cannot write {target}: {exc.strerror or exc}"
        raise TraceImportError(msg) from exc
    with_cache = sum(1 for c in calls if isinstance(c.context.get(ND_CACHE_CONTEXT_KEY), Mapping))
    builtins = len(cache.entries)
    click.echo(
        f"merged nd_builtin_cache from {with_cache} of {len(calls)} calls into {target} "
        f"({builtins} builtin{'s' if builtins != 1 else ''}, {len(conflicts)} conflict"
        f"{'s' if len(conflicts) != 1 else ''})",
        err=True,
    )
