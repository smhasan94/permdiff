"""``permdiff record``: trace recording helpers (FR-L11)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import click

from permdiff.models.limits import MAX_LINE_BYTES
from permdiff.record.claude_code import (
    DEFAULT_OUT,
    DEFAULT_SETTINGS,
    HOOK_COMMAND,
    append_line,
    hook_entry,
    is_installed,
    load_settings,
    merge_hook,
    stamp,
    write_settings,
)

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


AGENTS = ("claude-code",)


def _executable() -> str:
    """The absolute ``permdiff`` on PATH when there is one, else the bare command."""
    found = shutil.which("permdiff")
    return found if found else HOOK_COMMAND


@record_group.command("install")
@click.argument("agent", type=click.Choice(AGENTS))
@click.option("--write", is_flag=True, help="Merge the hook into the settings file.")
@click.option(
    "--settings",
    type=click.Path(path_type=Path, dir_okay=False),
    default=DEFAULT_SETTINGS,
    show_default=True,
    help="Claude Code settings file to edit.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=DEFAULT_OUT,
    show_default=True,
    help="JSONL file the hook appends to.",
)
def record_install(agent: str, write: bool, settings: Path, out: Path) -> None:
    """Print the PreToolUse hook entry for AGENT; --write merges it into the settings file."""
    del agent  # one choice today; the argument names the target for future agents
    settings_path = settings.expanduser()
    entry = hook_entry(out.expanduser(), executable=_executable())
    click.echo(json.dumps(entry, indent=2))
    if not write:
        click.echo(f"would add this PreToolUse hook to {settings_path} (pass --write)")
        return
    current = load_settings(settings_path)
    if is_installed(current):
        click.echo(f"already installed in {settings_path}; nothing changed")
        return
    backup = write_settings(settings_path, merge_hook(current, entry))
    if backup is not None:
        click.echo(f"backed up the previous file to {backup}")
    click.echo(f"installed the PreToolUse hook in {settings_path}")
