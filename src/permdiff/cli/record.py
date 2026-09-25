"""``permdiff record``: trace recording helpers (FR-L11)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from permdiff.models.limits import MAX_LINE_BYTES
from permdiff.record.claude_code import DEFAULT_OUT, append_line, stamp

PREFIX = "permdiff record: "


@click.group("record")
def record_group() -> None:
    """Record agent tool calls for permdiff."""


def _complain(reason: str) -> None:
    """One stderr line; stdout stays empty because Claude Code parses it."""
    click.echo(PREFIX + reason, err=True)


def _read_event() -> dict[str, object] | None:
    raw = sys.stdin.buffer.read(MAX_LINE_BYTES + 1)
    if len(raw) > MAX_LINE_BYTES:
        _complain(f"event is over the {MAX_LINE_BYTES >> 20} MiB limit; not recorded")
        return None
    if not raw.strip():
        _complain("empty stdin; nothing recorded")
        return None
    try:
        event = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        _complain(f"invalid JSON on stdin: {exc}")
        return None
    if not isinstance(event, dict):
        _complain("expected a JSON object on stdin")
        return None
    return event


@record_group.command("claude-code")
@click.option(
    "--out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=DEFAULT_OUT,
    show_default=True,
    help="JSONL file to append to.",
)
def record_claude_code(out: Path) -> None:
    """Claude Code PreToolUse hook: stamp stdin with ts and append it to --out.

    Never writes stdout and always exits 0, so it cannot block or alter a tool call.
    """
    try:
        event = _read_event()
        if event is None:
            return
        append_line(out.expanduser(), stamp(event))
    except OSError as exc:
        _complain(f"cannot write {out}: {exc.strerror or exc}")
    except Exception as exc:  # a recorder must never block the tool call
        _complain(f"unexpected error: {exc}")
