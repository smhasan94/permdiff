# Plan: E9 — `permdiff record`: Claude Code hook command and installer

**Source**: [03-epics.md](../03-epics.md) E9; FR-L11 (scoped 2026-09-25)
**Complexity**: Small (3 stories, about one day)
**Status**: in progress 2026-09-25 (S1, S2 done)

## Summary

Give the 0.2.0 `claude-code-hooks` input a one-command setup. `permdiff record
claude-code` is the hook command Claude Code runs before every tool call: it stamps the
stdin object with `ts` and appends it to a JSONL file, and it can never block or alter the
call. `permdiff record install claude-code` prints the `settings.json` entry and, with
`--write`, merges it in after a backup. No store, server, rotation, or other agents.

## Verified 2026-09-25 (re-read before starting)

- **Hook contract** (code.claude.com/docs/en/hooks, read via docs agent earlier today):
  `PreToolUse` stdin is one JSON object (`session_id`, `cwd`, `permission_mode`,
  `hook_event_name`, `tool_name`, `tool_input`, optional `tool_use_id`, `agent_id`,
  `agent_type`). A hook's **stdout is parsed** (`hookSpecificOutput.permissionDecision`
  and friends) and **exit code 2 blocks** the tool call; other non-zero codes are logged.
  So the recorder writes nothing to stdout and exits 0 on every path.
- **Settings shape** (hooks reference; a real `~/.claude/settings.json` on this machine):
  `{"hooks": {"PreToolUse": [{"matcher": "<regex>", "hooks": [{"type": "command",
  "command": "<shell>", "timeout": <seconds>}]}]}}`. An empty matcher matches every tool.
- **Importer contract** (E8-S2, `importers/claude_code/hooks.py`): `ts` must be an
  RFC 3339 timestamp with a zone; `hook_event_name != "PreToolUse"` lines are skipped
  silently; `tool_use_id` is used as the call id when present.
- **CLI patterns**: `PermdiffGroup.invoke` turns `PermdiffError` into exit 1 and
  `GateFailedError` into exit 2 (`cli/main.py`); subcommand groups live in their own module
  (`cli/setup.py`); `init` writes a file and refuses to overwrite without `--force`
  (`cli/init.py`); `MAX_LINE_BYTES` is 1 MiB (`models/limits.py`).

## Patterns to mirror

| Category | Source | Pattern |
|---|---|---|
| Command group | `src/permdiff/cli/setup.py` | `@click.group("setup")` with commands attached, registered in `cli/main.py` |
| File writing | `src/permdiff/cli/init.py` | explicit target option, refuse silent overwrite, `click.echo(f"wrote {target}")` |
| Errors | `permdiff.errors.ConfigError` | user-facing config problems raise `PermdiffError` subclasses (exit 1); the hook command is the exception and swallows everything |
| Immutability | `importers/claude_code/transcript.py` `_context` | build new dicts, never mutate the input mapping |
| Tests | `tests/integration/test_cli_convert.py` | `CliRunner().invoke(cli, [...])`, `tmp_path`, assert `exit_code`, `stdout`, `stderr` separately |
| Fixtures | `tests/fixtures/claude_code/hooks.jsonl` | the round-trip target for the recorder's output |

## Files to create or change

| File | Action | Why |
|---|---|---|
| `src/permdiff/record/__init__.py` | CREATE | package doc; exports |
| `src/permdiff/record/claude_code.py` | CREATE | pure helpers: `stamp`, `append_line`, `hook_entry`, `is_installed`, `merge_hook`, `load_settings`, `DEFAULT_OUT`, `DEFAULT_SETTINGS` |
| `src/permdiff/cli/record.py` | CREATE | `record` group: `claude-code` (hook) and `install AGENT` commands |
| `src/permdiff/cli/main.py` | UPDATE | `cli.add_command(record_group)` |
| `tests/unit/record/__init__.py`, `test_claude_code.py` | CREATE | helper tests: stamp keeps an existing `ts`, append creates 0600 and appends, merge is idempotent and preserves other keys |
| `tests/integration/test_cli_record.py` | CREATE | hook command paths (good, bad JSON, oversized, unwritable) all exit 0 with empty stdout; round-trip through `ClaudeCodeHooksImporter`; install print vs `--write`, backup, idempotence, unparsable settings |
| `docs/importers.md` | UPDATE | `permdiff record install claude-code` first, `jq` as the manual alternative |
| `README.md` | UPDATE | one paragraph in the Claude Code quickstart |
| `scripts/quickstart_check.sh` | UPDATE | pipe a sample event through the installed `permdiff record claude-code` and diff it with `--from claude-code-hooks` |
| `CHANGELOG.md` | UPDATE | Unreleased entry |
| `docs/03-epics.md` | UPDATE | statuses |

## Interfaces

```python
# record/claude_code.py
DEFAULT_OUT = Path("~/.claude/permdiff-hooks.jsonl")        # expanded at call time
DEFAULT_SETTINGS = Path("~/.claude/settings.json")
HOOK_COMMAND = "permdiff record claude-code"
TIMESTAMP_KEY = "ts"

def stamp(event: Mapping[str, Any], now: datetime | None = None) -> dict[str, Any]
#   new dict; adds ts = now (UTC, "%Y-%m-%dT%H:%M:%SZ") unless the event already has a ts
def append_line(path: Path, record: Mapping[str, Any]) -> None
#   mkdir parents; os.open(O_WRONLY|O_APPEND|O_CREAT, 0o600); one json.dumps line; raises OSError
def hook_entry(out: Path, executable: str = HOOK_COMMAND) -> dict[str, Any]
#   {"matcher": "", "hooks": [{"type": "command", "command": f"{executable} --out {shlex.quote(str(out))}", "timeout": 5}]}
def is_installed(settings: Mapping[str, Any]) -> bool
#   any PreToolUse entry with a hook whose command contains "record claude-code"
def merge_hook(settings: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]
#   returns a new settings dict with entry appended to hooks.PreToolUse (created if absent); input untouched
def load_settings(path: Path) -> dict[str, Any]
#   {} when absent; ConfigError("cannot parse <path>: ...") on bad JSON or a non-object

# cli/record.py
@click.group("record")                      # "Record agent tool calls for permdiff."
def record_group(): ...
@record_group.command("claude-code")        # --out PATH (default DEFAULT_OUT)
def record_claude_code(out):                # read stdin (cap MAX_LINE_BYTES + 1), stamp, append; every failure -> one stderr line, exit 0
@record_group.command("install")            # AGENT in {"claude-code"}; --write; --settings PATH; --out PATH
def record_install(agent, write, settings, out):
#   print json.dumps(entry, indent=2) and "would edit <settings>" (or "installed" / "already installed"); --write: backup to <settings>.bak then write pretty JSON
```

The hook command never raises: bad JSON, an oversized payload, and an unwritable file each
print `permdiff record: <reason>` to stderr and exit 0. Events other than `PreToolUse` are
appended as-is (plus `ts`); the importer skips them, so one entry can serve several hook
events later.

## Tasks

1. **E9-S1 hook command** — tests first: `stamp` (adds `ts`, keeps an existing one,
   deterministic with `now`), `append_line` (creates parents, mode 0600, appends two lines,
   propagates `OSError`), CLI paths (valid event → one line and empty stdout; bad JSON,
   1 MiB + 1 payload, and `--out` in an unwritable directory → exit 0, empty stdout, one
   stderr line, no file change), round-trip through `ClaudeCodeHooksImporter` comparing
   `tool.name`, `arguments`, `context`. Then implement; register the group.
2. **E9-S2 installer** — tests first: print mode writes nothing and shows the entry and
   path; `--write` creates the file, merges into an existing one with other keys and an
   existing `PreToolUse` list, writes `.bak` once, second run says "already installed" and
   changes nothing (compare bytes); bad JSON → exit 1 with the path and no `.bak`.
3. **E9-S3 docs, quickstart** — docs and README text; quickstart script step; CHANGELOG;
   statuses; run `scripts/quickstart_check.sh`.

## Test strategy

Unit tests for the pure helpers; integration tests through `CliRunner` with `input=` for
stdin and `tmp_path` for `--out` and `--settings`. The unwritable case uses a `tmp_path`
subdirectory with mode 0500 (skipped when running as root). No test touches `~/.claude`.

## Validation

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -q tests/unit/record tests/integration/test_cli_record.py
printf '%s\n' '{"hook_event_name":"PreToolUse","session_id":"s","cwd":"/p","tool_name":"Bash","tool_input":{"command":"ls"}}' \
  | uv run permdiff record claude-code --out /tmp/permdiff-hooks.jsonl; echo "exit=$?"
uv run permdiff convert --from claude-code-hooks /tmp/permdiff-hooks.jsonl
uv run permdiff record install claude-code --settings /tmp/settings.json --write
scripts/quickstart_check.sh
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| A recorder failure blocks the user's tool call | Low | exit 0 and silent stdout on every path; integration tests for each failure path; timeout 5 in the entry |
| A click usage error (unknown flag in a hand-edited entry) exits 2 and blocks calls | Low | the installer writes the entry; docs show the exact command; `permdiff record claude-code -h` documents the only flag |
| `--write` damages a user's `settings.json` | Low | backup first, parse before write, refuse on unparsable input, idempotent, pretty JSON; print mode is the default |
| Log file grows without bound | Medium | out of scope (not a store); docs say to rotate or truncate; the importer's record cap protects `diff` |
| `permdiff` not on PATH for Claude Code's shell | Medium | installer uses the absolute path of the running `permdiff` (`shutil.which`) when found, else the bare name, and prints which |

## Acceptance

- [ ] All three stories done and marked in `docs/03-epics.md`
- [ ] Validation passes; CI (`ci`, `bench`, `dogfood`) green
- [ ] A recorded event converts through `--from claude-code-hooks` and diffs with the E8 example policies
- [ ] Patterns mirrored: `setup` group, `init` file handling, `ConfigError`, `CliRunner` tests
