# Plan: E8 — Claude Code importer: transcripts and hook logs

**Source**: [03-epics.md](../03-epics.md) E8; FR-L3 (widened 2026-09-25), FR-5, FR-7
**Complexity**: Medium (3 stories, about two days)
**Status**: reviewed 2026-09-25 (code-review low: no findings; CI mypy scope fix in 1 follow-up commit)

## Summary

Read Claude Code session transcripts (`~/.claude/projects/<slug>/<session>.jsonl`) and
`PreToolUse` hook logs as `ToolCall` corpora, through one shared mapping. Transcripts need
no setup and carry timestamps and recorded denials; hook logs are the documented, stable
input. Ship auto-detection, `convert`, docs, and a README quickstart with an example policy
pair so a Claude Code user sees a real transition report in five minutes.

## Verified 2026-09-25 (re-read before starting)

- **Hooks reference** (code.claude.com/docs/en/hooks and hooks-guide, read via docs agent):
  `PreToolUse` stdin fields `session_id`, `prompt_id`, `transcript_path`, `cwd`,
  `permission_mode` (`default | plan | acceptEdits | auto | dontAsk | bypassPermissions`),
  `hook_event_name`, `tool_name`, `tool_input`, optional `agent_id`, `agent_type`. No
  timestamp, no user identity, no decision. MCP tools are named `mcp__<server>__<tool>`.
  The only documented append-to-file hook is a `jq -c '...' >> file` command; nothing
  official logs `PreToolUse` stdin, so the docs must show the hook.
- **Transcripts** are undocumented. Facts from 421 local files written by Claude Code
  2.1.282 (7,128 `tool_use` blocks): every `tool_use` line has `type: "assistant"`,
  `uuid`, `parentUuid`, `timestamp` (ISO 8601, `Z`, 24 chars, never missing), `sessionId`
  (always; `session_id` on 65%), `cwd`, `version`, `gitBranch`, `isSidechain`,
  `message.content[]` with `{type: "tool_use", id: "toolu_…", name, input}`.
  `wireToolInputs[id]` exists on 24% of lines and differs from `input` on 9% (Bash
  commands gain a `cd <cwd> && ` prefix): it is what ran, so it wins. Subagent
  transcripts live in `<session>/subagents/agent-<id>.jsonl` with `isSidechain: true`
  and `agentId`. Results: `type: "user"` lines with `{type: "tool_result", tool_use_id,
  content (str, or list of text/image/document/tool_reference parts), is_error}`,
  top-level `toolUseResult` (dict or str) and, on denials, `toolDenialKind` in
  `permission-rule` (389) | `user-rejected` (37) | `automode-blocked` (3). Two of 7,128
  calls had no result (session ended). Other line types: `mode`, `permission-mode`
  (`{type, permissionMode, sessionId}`), `attachment`, `hook_success`, `thinking`,
  `summary`, `total_tokens_reminder`. No MCP calls in the local corpus.
- **Caps**: `MAX_LINE_BYTES` is 1 MiB; `Write` inputs can exceed it, so such lines skip
  and count (not silently).
- **Pattern**: `read_lines` (`importers/lines.py`) takes a `(text, locator) -> ToolCall |
  None` parser; `None` skips silently. OTel counts `otel.principal_missing` in context
  and logs one warning; docs table per format in `docs/importers.md`.

## Patterns to mirror

| Category | Source | Pattern |
|---|---|---|
| Module layout | `src/permdiff/importers/custody.py` | constants, `_require`/`_mapping` helpers, `to_toolcall(event, locator)`, class with `name`, `detect(head)`, `read(...)` via `read_lines` |
| Sub-package | `src/permdiff/importers/otel/` | `__init__.py` exports the importer; `mapping.py` holds pure functions |
| Errors | `RecordRejected(reason)` per record; `TraceImportError` for file-level | skip-and-count by default, `strict` aborts |
| Principal | `importers/otel/mapping.py:principal_of` | `--principal-from` path, `UNKNOWN_PRINCIPAL`, `context["<fmt>.principal_missing"]`, one warning |
| Options | `registry._builtins(**options)` | constructor kwargs (`principal_from`) via `TypeError` fallback |
| Tests | `tests/unit/importers/test_custody.py`, `tests/fixtures/custody/README.md` | fixture files with a `SOURCE` README, one test per AC, `registry` detection tests |
| Docs | `docs/importers.md` OTel section | prose, dated conventions, mapping table |

## Files to create or change

| File | Action | Why |
|---|---|---|
| `src/permdiff/importers/claude_code/__init__.py` | CREATE | exports `ClaudeCodeImporter`, `ClaudeCodeHooksImporter`, format names |
| `src/permdiff/importers/claude_code/mapping.py` | CREATE | shared: tool name/server split, resource inference, principal, context, `build_toolcall(...)` |
| `src/permdiff/importers/claude_code/transcript.py` | CREATE | `ClaudeCodeImporter`: pass 1 result index, pass 2 line loop with a stateful parser (last `permission_mode`) |
| `src/permdiff/importers/claude_code/hooks.py` | CREATE | `ClaudeCodeHooksImporter`: `PreToolUse` lines, `ts` required |
| `src/permdiff/importers/lines.py` | UPDATE | `read_lines_multi` (parser returns a sequence); `read_lines` wraps it |
| `src/permdiff/importers/registry.py` | UPDATE | add both to `_BUILTIN` after `OtelImporter` |
| `src/permdiff/cli/settings.py` | UPDATE | `--principal-from` help mentions `env:USER` |
| `tests/fixtures/claude_code/*.jsonl`, `README.md` | CREATE | `session.jsonl` (scrubbed real lines: allow, permission-rule deny, user-rejected, wire-input diff, no-result call, permission-mode line, MCP-named call, oversized Write), `subagent.jsonl`, `hooks.jsonl` (from the documented hook), `hooks_no_ts.jsonl`, `invalid.jsonl` |
| `tests/unit/importers/claude_code/test_transcript.py`, `test_hooks.py`, `test_mapping.py` | CREATE | per-AC tests |
| `tests/unit/importers/test_registry.py` | UPDATE | detection order and `--from` mismatch for both |
| `tests/integration/test_cli_convert.py` | UPDATE | round-trip for both formats |
| `examples/claude-code/policy_base/rules.py`, `policy_head/rules.py`, `README.md` | CREATE | demo-engine rule tables for the quickstart |
| `tests/integration/test_examples_claude_code.py` | CREATE | `permdiff diff` on the fixture with the example policies: exit 2, expected transition classes |
| `docs/importers.md` | UPDATE | two sections and mapping tables; hook snippet; undocumented-format caveat |
| `README.md` | UPDATE | "Diff your Claude Code sessions" |
| `scripts/quickstart_check.sh` | UPDATE | run the Claude Code quickstart from the installed package |
| `CHANGELOG.md` | UPDATE | 0.2.0 Unreleased: both importers |
| `docs/03-epics.md` | UPDATE | statuses |

## Interfaces

```python
# importers/claude_code/mapping.py
FORMAT_TRANSCRIPT = "claude-code"
FORMAT_HOOKS = "claude-code-hooks"
AGENT_ID = "claude-code"
UNKNOWN_PRINCIPAL = "unknown"                       # same literal as otel
DENIAL_KINDS = frozenset({"permission-rule", "user-rejected", "automode-blocked"})
RESOURCE_KEYS = (("file_path", "file"), ("notebook_path", "file"), ("path", "file"), ("url", "url"))

def split_tool(name: str) -> tuple[str | None, str | None]   # ("server", "mcp") for mcp__s__t, else (None, None)
def resource_of(tool: str, arguments: Mapping | None) -> dict   # Bash -> {"type": "shell"}; file/url keys -> id
def principal_of(record: Mapping, principal_from: str | None) -> tuple[str, bool]
#   principal_from: "env:<VAR>" -> os.environ, else a top-level key of the line/object
def build_toolcall(*, call_id, timestamp, tool, arguments, record, principal_from,
                   context, recorded_effect, fmt, locator) -> ToolCall   # RecordRejected on ValidationError

# importers/claude_code/transcript.py
class ClaudeCodeImporter:
    name = "claude-code"
    def __init__(self, principal_from: str | None = None) -> None
    def detect(self, head: bytes) -> bool   # first non-blank line: JSON object with "type" and ("sessionId" or "session_id"), not a hooks line
    def read(self, path, *, strict=False, max_records=DEFAULT_MAX_RECORDS) -> ImportResult
#   pass 1: index_results(path) -> dict[tool_use_id, denial_kind | None]
#           only lines containing b'"tool_result"' are parsed; bad JSON ignored here (pass 2 reports it)
#   pass 2: read_lines_multi(path, _Parser(index, principal_from)); the parser tracks
#           permission_mode from "permission-mode" lines, returns () for non-tool lines, one
#           ToolCall per tool_use block, and raises RecordRejected for a block missing id/name
#           or a line missing timestamp.

# importers/claude_code/hooks.py
class ClaudeCodeHooksImporter:
    name = "claude-code-hooks"
    def detect(self, head) -> bool   # first non-blank line has "hook_event_name"
    def read(...)                    # read_lines with _parse_hook_line: PreToolUse only; ts required
```

`context` keys (transcript): `session_id`, `cwd`, `git_branch`, `permission_mode`,
`claude_code.version`, `claude_code.sidechain` (bool), `claude_code.agent_id`,
`claude_code.denial_kind`, `claude_code.model_input_differs`,
`claude_code.principal_missing`. Hook log: `session_id`, `cwd`, `permission_mode`,
`claude_code.agent_id`, `claude_code.agent_type`, `claude_code.principal_missing`.

Documented hook (`docs/importers.md`, README):

```json
{"hooks": {"PreToolUse": [{"matcher": "", "hooks": [{"type": "command",
  "command": "jq -c '. + {ts: (now | todate)}' >> \"$HOME/.claude/permdiff-hooks.jsonl\""}]}]}}
```

Example policies (`examples/claude-code/`): base allows `Bash`, `Read`, `Glob`, `Grep`,
`Edit`, `Write`, default deny; head adds `require_approval` for `Bash` when the command
matches a recursive forced delete or a forced push, denies `Write`/`Edit` whose
`file_path` is outside `context.cwd`, and allows `WebFetch` (a widening the report flags).

## Tasks

1. **E8-S1 transcript** — `read_lines_multi` with tests; mapping functions with table
   tests (tool split, resource, principal incl. `env:`); result index; importer tests per
   AC-L3.1 to AC-L3.5 on `session.jsonl` and `subagent.jsonl`; oversized-line skip
   counted; registry detection.
2. **E8-S2 hooks** — generate `hooks.jsonl` by running the documented hook command over
   real `PreToolUse` stdin captured locally, scrub, record the command in the fixture
   README; tests AC-L3.6 to AC-L3.8; `hook_event_name` skip; missing `ts` reason names
   the hook.
3. **E8-S3 registry, convert, docs, quickstart** — detection order tests; convert
   round-trip; `examples/claude-code` policies plus an integration test that runs
   `permdiff diff --engine python:... --policy <tmp git repo>` with base and head commits
   built from the two example directories (as `test_cli_diff.py` does) and asserts exit 2
   and the transition classes; README section; `quickstart_check.sh` runs the same from
   the installed package; docs tables; CHANGELOG; statuses.

## Test strategy

Fixtures are real local lines, scrubbed (paths under `/home/dev/project`, principal-free,
command text replaced with harmless equivalents, `content` truncated), with a `SOURCE`
README naming Claude Code 2.1.282 and the date. Unit tests per AC; one integration test per
CLI surface (`convert`, `diff` with the example policies). Property test: convert
round-trip equality on canonical fields, as E5-S4.

## Validation

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest tests/unit/importers tests/integration/test_cli_convert.py tests/integration/test_examples_claude_code.py
uv run permdiff convert --from claude-code tests/fixtures/claude_code/session.jsonl -o /tmp/cc.jsonl
scripts/quickstart_check.sh
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Transcript format changes without notice | High | fixtures pinned to a version; parser ignores unknown keys and line types; docs caveat; hook log as the documented fallback |
| Transcripts hold file contents and secrets in `Write`/`Edit` inputs | High | existing redaction applies to every report; README warns to keep transcript diffs local (`--format terminal` prints principals verbatim only) |
| 1 MiB line cap drops large `Write` calls | Medium | skipped-and-counted with the locator; documented |
| `wireToolInputs` semantics not documented | Medium | prefer it (it is what ran); flag `claude_code.model_input_differs` when it differs from `input` |
| Principal absent in both sources | High | `--principal-from env:USER` documented in the quickstart; `unknown` with a note otherwise |
| Multi-block lines vs `read_lines` one-call contract | Low | `read_lines_multi` in `lines.py`, unit-tested; `read_lines` becomes a thin wrapper |

## Acceptance

- [ ] All three stories done and marked in `docs/03-epics.md`
- [ ] Validation passes; CI (`ci`, `bench`, `dogfood`) green
- [ ] `permdiff diff --from claude-code` on the fixture with the example policies exits 2 and lists the expected transitions
- [ ] Patterns mirrored: `read_lines`, `RecordRejected`, `--principal-from`, fixture README
