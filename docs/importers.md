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

Arrives with E5-S2.
