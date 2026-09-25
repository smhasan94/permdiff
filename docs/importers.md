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

## Auto-detection and `permdiff convert`

`--from auto` (the default) sniffs each file in the order permdiff JSONL, Custody, OTel and
logs the choice (`--verbose`). `--from NAME` forces an importer and fails with a clear
message when the file is recognizably another format.

```
permdiff convert --from otel traces/otel/*.json -o traces/otel.jsonl
permdiff convert --from custody custody-export.jsonl -o traces/custody.jsonl
```

`convert` writes canonical JSONL that round-trips through the JSONL importer without loss
of the canonical fields; each record keeps its original `source` for provenance.
