# Changelog

## Unreleased

- OPA decision-log importer (FR-L4): `--from opa-decision-log` reads sink JSON arrays and
  console logs, imports events whose `input` is a permdiff `ToolCall`, maps `result` to the
  recorded effect (`--decision` unwraps package-shaped results), and keeps `decision_id`,
  `path`, labels, bundle revisions, and `erased`/`masked` paths in context. Foreign `input`
  shapes are skipped with the first validation error named.
- `permdiff convert --nd-cache-out FILE` merges the events' `nd_builtin_cache` into the file
  `--nd-cache` loads, reporting conflicts (first value wins; `--strict` aborts).
- Importers now receive only the options their constructors accept, so `--principal-from`
  and `--decision` can be given together.

## 0.3.0 (2026-09-25)

- `permdiff record claude-code`, a Claude Code `PreToolUse` hook command that stamps the
  event with `ts` and appends it to `~/.claude/permdiff-hooks.jsonl` (never writes stdout,
  always exits 0), and `permdiff record install claude-code [--write]` to print or merge
  the `settings.json` entry (FR-L11).

## 0.2.0 (2026-09-25)

- Claude Code importers (FR-L3): `--from claude-code` reads session transcripts from
  `~/.claude/projects/<slug>/` (one call per `tool_use` block, recorded deny from
  `toolDenialKind`, `wireToolInputs` preferred over the model's input);
  `--from claude-code-hooks` reads `PreToolUse` stdin logged by a documented `jq` hook that
  adds `ts`. Both auto-detect, convert, and take `--principal-from env:VAR` or a top-level
  key. `examples/claude-code/` holds a policy pair for the README quickstart. The transcript
  format is undocumented; this release is pinned to what Claude Code 2.1.282 writes and
  ignores unknown keys and line types.
- `--principal-from` now also applies to the Claude Code importers (`env:VAR` or a
  top-level key of the record).

## 0.1.0 (2026-09-25)

First release. `terraform plan` for AI agent permission changes.

- `permdiff diff` replays recorded tool calls against a policy at two git refs and reports
  widening, tightening, require-approval, can't-evaluate, and attribution changes with
  exit codes for CI (`--fail-on widen|any-change|cant-evaluate|none`, `--allow-widening`).
- Engines: OPA 1.21.0 (pinned, checksum-verified download; batch evaluation with
  per-call time injection, restricted capabilities, `--nd-cache` replay of recorded
  nondeterministic builtins, `--undefined deny|error`), Cedar via `permdiff[cedar]`
  (schema validation, request templates, `@require_approval`), and Python callables.
- Importers: permdiff JSONL, Custody `custody.trace.v1` (spec-derived), OpenTelemetry
  GenAI `execute_tool` and MCP `tools/call` spans (OTLP/JSON and JSONL, parent-span
  argument fallback), auto-detection, and `permdiff convert`.
- Reports: terminal, markdown PR comment, JSON (versioned envelope with a shipped
  schema), SARIF 2.1.0; grouping by tool, resource type, agent, principal, or reason;
  deterministic samples; redaction by default with hashed principals outside the
  terminal.
- `permdiff.toml` configuration with environment and flag precedence, `permdiff init`,
  `permdiff check`, `permdiff render --from-json`, `permdiff schema`, `permdiff setup opa`,
  `permdiff demo` (Python, OPA, or Cedar variants of the bundled example).
- GitHub Action (`action.yml`) with a sticky PR comment, job summary and artifact
  fallback for fork PRs, SARIF output, and exit-code propagation.
- Benchmark and CI regression gate: 100,000 calls end to end in 6.5 s (Python) and
  11.8 s (OPA) under 1 GiB on the reference laptop.
