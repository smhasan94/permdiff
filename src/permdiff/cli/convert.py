"""``permdiff convert``: write any supported trace format as canonical permdiff JSONL (FR-7)."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from permdiff import api
from permdiff.errors import TraceImportError
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
@click.option("--max-records", type=int, default=DEFAULT_MAX_RECORDS, show_default=True)
@click.option(
    "--principal-from",
    default=None,
    help="Principal source: OTel attribute path, or env:VAR / a top-level key for Claude Code.",
)
def convert_cmd(
    files: tuple[str, ...],
    fmt: str,
    output: Path | None,
    strict: bool,
    max_records: int,
    principal_from: str | None,
) -> None:
    """Convert Custody or OTel traces (or any importer's input) to permdiff JSONL."""
    options = {"principal_from": principal_from} if principal_from else {}
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
