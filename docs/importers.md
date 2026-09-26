# Trace importers

Every importer produces the canonical `ToolCall` (`permdiff schema toolcall`). `--from auto`
sniffs the first record of each file; `--from <name>` forces one.

## permdiff JSONL (`jsonl`)

One `ToolCall` JSON object per line, as-is. Malformed lines are skipped and counted
(`--strict` aborts on the first). Non-UTF-8 input, lines over 1 MiB, and nesting deeper
than 32 levels are rejected.

## Custody (`custody`)

Reads `custody.trace.v1` events, one per line. **Derived from Custody's planning spec
(`PLAN.md` §5, commit bb81683, read 2026-09-25); Custody has not emitted real traces yet,
so the mapping is unverified against real output.** Extra fields are ignored so additive
schema changes keep working; any other `schema` value is rejected.

| Custody | ToolCall |
|---|---|
| `id` | `id` |
| `ts` | `timestamp` |
| `actor.user` | `principal.id` (type `user`); `actor.host` → `principal.attrs.host` |
| `actor.agent` | `agent.id` |
| `action.name` | `tool.name`; `action.type` → `tool.type` (`mcp_call` also sets `tool.server = mcp`) |
| `action.input_redacted` | `arguments`; absent (digest-only export) → `null` and `context["custody.digest_only"] = true` |
| `action.type`, `action.repo` | `resource.type`, `resource.id` |
| `session_id`, `workspace`, `source`, `action.cwd`, `action.repo`, `action.branch` | `context` |
| `action.input_digest`, `decision.rule_ids` | `context["custody.input_digest"]`, `context["custody.rule_ids"]` |
| `decision.verdict` | `recorded.effect`: `allow` → allow, `block` → deny, `warn`/`observe` → allow with `context["custody.verdict"]` keeping the original |
| `decision.policy_hash` | `recorded.policy_hash` |

Digest-only events give argument-dependent rules nothing to read, so those calls report
`can't evaluate` (missing context); the `custody.digest_only` flag in the context lets a
policy or a reader tell that apart from a genuinely missing attribute.

## OpenTelemetry GenAI (`otel`)

Reads OTLP/JSON trace documents (`resourceSpans → scopeSpans → spans`), either one
document per file or one per line (JSONL), as written by the OTLP file exporter or a
collector's file exporter. Only tool spans are imported: `gen_ai.operation.name ==
execute_tool`, span names starting `execute_tool `, and MCP `tools/call` spans
(`mcp.method.name`). Everything else (chat, agent, embedding spans) is skipped.

The conventions tracked are OpenTelemetry semantic-conventions-genai `main` as of
2026-09-25, which is still Development stability; attribute names may change and the
alias table in `importers/otel/mapping.py` absorbs renames (`gen_ai.system` →
`gen_ai.provider.name` today).

| OTel | ToolCall |
|---|---|
| `gen_ai.tool.call.id`, else `spanId` | `id` |
| `startTimeUnixNano` | `timestamp` |
| `enduser.id` / `user.id` on the span, then on the resource; else `--principal-from PATH` (`attr.<key>`, `resource.attr.<key>`); else `unknown` with `context["otel.principal_missing"] = true` and a warning | `principal.id` |
| `gen_ai.agent.name`, else `gen_ai.agent.id`, else resource `service.name` | `agent.id` |
| `gen_ai.tool.name` (else the span name after `execute_tool ` / `tools/call `) | `tool.name`; `gen_ai.tool.type` → `tool.type`; MCP spans set `tool.server = mcp` |
| `gen_ai.tool.call.arguments` (Opt-In; JSON text or kvlist) | `arguments` |
| ancestor span `gen_ai.output.messages` `tool_call` part with the same id (or a unique part for the tool), or a deprecated `gen_ai.choice` event | `arguments` when the span carries none |
| `gen_ai.conversation.id`, `mcp.session.id`, `gen_ai.provider.name`, trace and span ids | `context` |

Most real OTel data does not record arguments (they are Opt-In), so argument-dependent
rules report `can't evaluate` for those calls; the report says so.

## Claude Code transcripts (`claude-code`)

Reads the session transcripts Claude Code already writes to
`~/.claude/projects/<slug>/<session>.jsonl` (subagent transcripts sit in
`<session>/subagents/`). No setup: point `--traces` at the files. The format is
**undocumented**; the mapping below was derived from transcripts written by Claude Code
2.1.282 on 2026-09-25 (`tests/fixtures/claude_code/README.md`). Unknown keys and line
types are ignored, so additive changes keep working; a breaking change shows up as
skipped records with reasons.

| Transcript | ToolCall |
|---|---|
| `message.content[].id` of each `tool_use` block on an `assistant` line | `id` (one call per block) |
| line `timestamp` | `timestamp` |
| `--principal-from env:VAR` or a top-level key of the line; else `unknown` with `context["claude_code.principal_missing"] = true` and one warning | `principal.id` |
| `claude-code`, line `version` | `agent.id`, `agent.version` |
| block `name`; `mcp__<server>__<tool>` sets `tool.server` and `tool.type = mcp` | `tool` |
| `wireToolInputs[id]` (what ran; `context["claude_code.model_input_differs"]` when it differs), else block `input` | `arguments` |
| `Bash` → `shell`; `file_path` / `notebook_path` / `path` → `file`; `url` → `url` | `resource` |
| `sessionId`, `cwd`, `gitBranch`, last `permission-mode` line, `isSidechain`, `agentId` | `context` (`session_id`, `cwd`, `git_branch`, `permission_mode`, `claude_code.sidechain`, `claude_code.agent_id`) |
| paired `tool_result` line: `toolDenialKind` (`permission-rule`, `user-rejected`, `automode-blocked`) → `deny`, kept in `context["claude_code.denial_kind"]`; a result without it → `allow`; no result → unset | `recorded.effect` |

Transcripts contain what the agent read and wrote, including file contents in `Write`
and `Edit` inputs. Reports redact argument values by default; keep `--redact none` and
`--show-args` for local use.

## Claude Code hook logs (`claude-code-hooks`)

The documented, stable input: `PreToolUse` hook stdin
([reference](https://code.claude.com/docs/en/hooks), read 2026-09-25), one object per
line. The stdin carries no timestamp, so the hook must add one. permdiff ships the hook:

```
permdiff record install claude-code            # prints the settings.json entry
permdiff record install claude-code --write    # merges it into ~/.claude/settings.json (backup first)
```

The entry runs `permdiff record claude-code --out ~/.claude/permdiff-hooks.jsonl` before
every tool call. The recorder stamps the event with `ts`, appends one line, never writes
to stdout, and always exits 0, so it cannot block or change a tool call. The file is not
rotated; truncate it when you like. Without permdiff on Claude Code's `PATH` (the
installer writes the absolute path it finds), or if you prefer no Python in the hook, the
manual equivalent with `jq` is:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "jq -c '. + {ts: (now | todate)}' >> \"$HOME/.claude/permdiff-hooks.jsonl\""
          }
        ]
      }
    ]
  }
}
```

| Hook stdin | ToolCall |
|---|---|
| `tool_use_id` when present, else a derived id (AC-1.3) | `id` |
| `ts` (added by the hook; a line without it is rejected with the hook command in the reason) | `timestamp` |
| `--principal-from env:VAR` or a top-level key; else `unknown` as above | `principal.id` |
| `tool_name`, `tool_input` | `tool`, `arguments` (resource as above) |
| `session_id`, `cwd`, `permission_mode`, `agent_id`, `agent_type` | `context` |
| never set: hooks run before the decision | `recorded.effect` |

Lines for other hook events (`PostToolUse`, …) in the same file are skipped silently.

## OPA decision logs (`opa-decision-log`)

Reads the decision logs an OPA server emits: the JSON array a remote sink receives
(gunzip it first) or console logging (`decision_logs.console: true`; one event per line
with `type: "openpolicyagent.org/decision_logs"`, other server log lines skipped). Verified
2026-09-26 against the pinned OPA 1.21.0; fixtures in `tests/fixtures/opa_log/` are a live
capture.

By default only events whose `input` is a permdiff `ToolCall` import, which is what a
deployment gets when it sends OPA the same `input` permdiff's engine does. Any other
`input` shape is skipped and counted with the first validation error named; nothing is
guessed.

For other shapes, declare the mapping with `--input-map target=source` (repeatable, or
comma-separated; `traces.input_map` in `permdiff.toml`, `PERMDIFF_TRACES_INPUT_MAP` in the
environment). `target` is a dotted `ToolCall` path: `id`, `timestamp`, `principal.id`,
`principal.type`, `principal.attrs.<k>`, `agent.id`, `agent.version`, `agent.attrs.<k>`,
`tool.name`, `tool.server`, `tool.type`, `arguments` (an object) or `arguments.<k>` entries
(not both),
`resource.type`, `resource.id`, `resource.attrs.<k>`, `context.<k>`. `source` is a dotted
path into the event's `input` (list indexes as integers), `event.<field>` for the event
itself, or `const:<text>`. With a map, `id` defaults to the event's `decision_id` and
`timestamp` to the event's `timestamp`; a required target (`principal.id`, `agent.id`,
`tool.name`) that resolves to nothing skips the event with the target and source named.

An HTTP-authorization deployment whose input is `{"method": "GET", "path": "/salary/bob",
"user": {"name": "bob"}}`:

```
permdiff diff --from opa-decision-log --traces decisions.jsonl \
  --input-map principal.id=user.name --input-map agent.id=const:api-gateway \
  --input-map tool.name=method --input-map resource.type=const:http --input-map resource.id=path \
  --decision data.http.authz.allow ...
```

| Decision-log event | ToolCall |
|---|---|
| `input` (must validate as a `ToolCall`) | the call itself: `id`, `timestamp`, `principal`, `agent`, `tool`, `arguments`, `resource`, `context` |
| `result`, through the OPA engine's rules (object with `effect`, boolean, effect string); with `--decision data.pkg.rule`, a package-shaped object is unwrapped at `rule` | `recorded.effect`; an unmappable result leaves it unset and puts the reason in `context["opa.result_unmapped"]` |
| `bundles.<name>.revision` | `recorded.policy_hash` when exactly one bundle; all of them in `context["opa.bundles"]` |
| `decision_id`, `path`, `timestamp`, `labels`, `requested_by`, `erased`, `masked` | `context["opa.decision_id"]`, `opa.path`, `opa.logged_at`, `opa.labels`, `opa.requested_by`, `opa.erased`, `opa.masked` |
| `nd_builtin_cache` (when `nd_builtin_cache: true` in the OPA config) | `context["opa.nd_builtin_cache"]` |

Replaying a log against a policy that calls nondeterministic builtins needs the values
the deployment saw. `convert` merges them:

```
permdiff convert --from opa-decision-log decisions.jsonl -o traces.jsonl --nd-cache-out nd.json
permdiff diff --engine opa --nd-cache nd.json --traces traces.jsonl ...
```

The first recorded value wins when two events disagree for the same builtin and
arguments; every conflict is printed with both decision ids, and `--strict` aborts instead.

## Auto-detection and `permdiff convert`

`--from auto` (the default) sniffs each file in the order permdiff JSONL, Custody, OTel, Claude Code
hook log, Claude Code transcript, OPA decision log and logs the choice (`--verbose`). `--from NAME` forces an importer and fails with a clear
message when the file is recognizably another format.

```
permdiff convert --from otel traces/otel/*.json -o traces/otel.jsonl
permdiff convert --from custody custody-export.jsonl -o traces/custody.jsonl
```

`convert` writes canonical JSONL that round-trips through the JSONL importer without loss
of the canonical fields; each record keeps its original `source` for provenance.
