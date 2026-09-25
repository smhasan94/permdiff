# permdiff: product requirements

*Status: Phase 2 deliverable, 2026-09-25. Builds on [01-overview.md](01-overview.md).
Decisions in [decisions.md](decisions.md). All open questions were answered on 2026-09-25;
see §9 and [decisions.md](decisions.md).*

## 1. Goals

1. A developer with an authorization policy in git and any tool-call log gets
   a real transition report within five minutes of reading the README.
2. A policy PR that widens agent permissions on recorded traffic cannot merge
   silently: the PR shows the widening and CI fails by default.
3. Every recorded call ends in exactly one bucket. Nothing is silently
   treated as allowed, dropped, or double-counted.
4. Trace PII never reaches a PR comment, SARIF alert, or JSON artifact under
   default settings.
5. Works offline, from a single `pip install`, with no service to run.

## 2. Non-goals

See [01-overview.md §5](01-overview.md#5-non-goals). Restated as requirements
boundaries: no runtime enforcement, no trace collection, no LLM replay, no
symbolic analysis, no policy language, no legitimacy judgment, no hosted
component, no reimplementation of engine semantics.

## 3. Target users and personas

| Persona | Situation | What they need from permdiff |
|---|---|---|
| **Platform engineer, "Priya"** | Owns `policy/` (Rego) for an internal agent platform; reviews 5–10 policy PRs a week | A PR comment that says what changes on last week's traffic, and a CI gate on widening |
| **Security engineer, "Marcus"** | Approves agent tool access; does not write Rego daily | A readable summary by tool with counts, and a hashed-principal sample list he can trust not to leak |
| **Agent developer, "Lena"** | Iterates on a Cedar policy locally with a Claude Code agent | `permdiff diff --head WORKTREE` in a loop, fast, with argument values visible locally |
| **Control-plane author, "Custody"** | Ships a runtime that emits traces and wants a policy-PR check without building one | An importer for its trace format and a stable Python API |
| **Custom-engine team** | Has a YAML rules engine with a Python SDK | The Python callable adapter and the JSON output |

## 4. Functional requirements

Each FR has acceptance criteria (AC). "v0.1" or "later" marks scope.

### Schema and importers

**FR-1 Canonical `ToolCall` schema** (v0.1)
The package defines `ToolCall` as specified in the overview §3.2 and publishes
its JSON Schema.
- AC-1.1 `ToolCall` validates required fields (`id`, `timestamp`, `principal.id`,
  `agent.id`, `tool.name`) and rejects records missing them with the record
  locator in the error.
- AC-1.2 `arguments`, `*.attrs`, and `context` accept arbitrary JSON.
- AC-1.3 `permdiff schema` prints the JSON Schema; the schema is also shipped
  as a file in the package.
- AC-1.4 Records exceeding limits (line > 1 MiB, nesting > 32, corpus > a
  configurable cap defaulting to 1,000,000 records) are rejected with a clear
  error, not truncated.

**FR-2 permdiff JSONL importer** (v0.1)
One `ToolCall` JSON object per line.
- AC-2.1 Parses 100K lines within the performance budget (NFR-P1).
- AC-2.2 A malformed line reports file and line number; `--strict` aborts,
  default skips and counts the skip in the report footer.
- AC-2.3 Non-UTF-8 input is rejected.

**FR-3 Custody importer** (v0.1, spec-derived)
Reads `custody.trace.v1` events (Custody `PLAN.md` §5).
- AC-3.1 Maps `actor.user`→principal, `actor.agent`→agent, `action.name`→tool,
  `action.input_redacted`→arguments, `ts`→timestamp, `decision.verdict`→
  `recorded.effect` (`allow`→allow, `block`→deny, `warn`/`observe`→allow with
  a note), `decision.policy_hash`→`recorded.policy_hash`, `id`→id.
- AC-3.2 Events with `input_redacted` absent (digest-only) import with
  `arguments = null` and the report attributes resulting `missing_context`
  errors to "digest-only trace".
- AC-3.3 Unknown `schema` values are rejected; fixtures cover every `action.type`.
- AC-3.4 Docs state the importer is derived from the spec, not verified
  against real Custody output.

**FR-4 OpenTelemetry GenAI importer** (v0.1, decided 2026-09-25)
Reads OTLP/JSON (`resourceSpans`) files and JSONL (one `TracesData` per line).
- AC-4.1 Imports spans with `gen_ai.operation.name == "execute_tool"` or name
  prefix `execute_tool ` / `tools/call `.
- AC-4.2 Maps `gen_ai.tool.name`→tool, `gen_ai.tool.call.id`→id,
  `gen_ai.tool.call.arguments` (string or kvlist)→arguments,
  `gen_ai.agent.name|id`→agent, `enduser.id|user.id` (span, then resource)
  →principal, `gen_ai.conversation.id`→`context.session_id`,
  `startTimeUnixNano`→timestamp.
- AC-4.3 When arguments are absent, falls back to the parent chat span's
  `gen_ai.output.messages` `tool_call` part with matching id.
- AC-4.4 Accepts deprecated `gen_ai.system` and `gen_ai.choice` as aliases.
- AC-4.5 `--principal-from <attr path>` overrides principal mapping.

**FR-5 Format detection and selection** (v0.1)
- AC-5.1 `--from auto` sniffs the first record (permdiff JSONL, Custody,
  OTLP) and reports which importer was chosen.
- AC-5.2 `--from <name>` forces an importer; mismatch is an error.

**FR-6 Trace filtering** (v0.1)
- AC-6.1 `--since 7d|<ISO>` and `--until` filter on `timestamp`; the report
  header shows the effective window and call count.
- AC-6.2 `--tool GLOB`, `--agent GLOB`, `--principal GLOB` filter; counts of
  filtered-out calls appear in the footer.

**FR-7 `permdiff convert`** (v0.1)
- AC-7.1 `permdiff convert --from otel|custody FILE... -o out.jsonl` writes
  permdiff JSONL; round-trips through FR-2 losslessly for the canonical fields.

### Policy loading

**FR-8 Git-aware policy loading** (v0.1)
- AC-8.1 `--base REF --head REF` resolve via `git rev-parse --verify`; invalid
  refs fail with exit 1 and the git message.
- AC-8.2 Policy directory at each ref is extracted with `git archive` into a
  0700 temp dir removed on exit, including on error.
- AC-8.3 `--head WORKTREE` copies the working directory's policy path.
- AC-8.4 Report header includes both resolved SHAs, the policy path, and
  whether head was WORKTREE.
- AC-8.5 No shell interpolation anywhere; git is invoked with argument lists.
- AC-8.6 Works when run from a subdirectory of the repo and in a shallow
  clone with the refs present; a missing ref suggests `fetch-depth: 0`.

### Evaluation

**FR-9 Evaluator interface** (v0.1)
- AC-9.1 A `Protocol` with `prepare(policy_dir) -> Handle` (compile once per
  ref) and `evaluate(handle, calls: Iterable[ToolCall]) -> Iterable[Decision]`.
- AC-9.2 Adapters are selected by `--engine` and discoverable via entry points
  (`permdiff.evaluators`) so third parties can ship adapters.
- AC-9.3 `Decision` and error kinds per overview §3.3.

**FR-10 OPA evaluator** (v0.1)
- AC-10.1 Uses a pinned `opa` binary (version in package metadata; SHA-256
  per platform); downloads on first use to the user cache; `--opa-bin` and
  `PERMDIFF_OPA_BIN` override; `permdiff setup opa` prefetches.
- AC-10.2 One `opa eval` process per ref evaluates the whole corpus using a
  generated shim and `data.permdiff.cases`; 100K calls per ref within NFR-P1.
- AC-10.3 `--decision data.x.y` selects the rule; default from config.
- AC-10.4 Result mapping: object with `effect` (+ optional `reason`, `reasons`)
  or boolean; unknown `effect` strings are `error/unsupported`, never allow.
- AC-10.5 Per-call `with time.now_ns as <trace ts>`; a fixture with a
  business-hours rule flips correctly between two timestamps.
- AC-10.6 Runs with `--strict-builtin-errors` and a capabilities file that
  omits `http.send`, `net.lookup_ip_addr`, `rand.intn`, `uuid.rfc4122`,
  `opa.runtime`; a policy using one fails compilation for that ref and every
  call is `error/nondeterministic` naming the builtin.
- AC-10.7 `--nd-cache FILE` (OPA `nd_builtin_cache` shape) re-enables the
  listed builtins via `with` overrides using recorded values; a call whose
  lookup is missing from the cache is `error/nondeterministic`.
- AC-10.8 Undefined results (rule did not fire) map to `deny` only when the
  config says `undefined = "deny"` (default) and are otherwise
  `error/eval_error`; the choice is printed in the header.
- AC-10.9 `--v0-compatible` passthrough.
- AC-10.10 Determining rule attribution: file and line from `opa eval
  --explain=fails`-free approach is not available in batch; v0.1 reports the
  `reason` string and the decision path; line-level attribution is later.

**FR-11 Cedar evaluator** (v0.1, extra `permdiff[cedar]`)
- AC-11.1 Loads `*.cedar`, one `*.cedarschema`, and `entities.json` from the
  policy dir; validates policies against the schema and reports errors per ref.
- AC-11.2 Request templates for principal, action, resource (config); Cedar
  `context` = `arguments` ∪ `context` ∪ `{"now": <RFC 3339 timestamp>}`.
- AC-11.3 Uses `is_authorized_batch`; 100K calls per ref within NFR-P1 or the
  PRD records the measured number.
- AC-11.4 `require_approval` = Deny where every determining policy carries
  `@require_approval` (annotation name configurable); a Deny with any plain
  forbid stays `deny`.
- AC-11.5 Evaluation errors (missing entity, missing context attribute) are
  `error/missing_context` with the attribute or entity named.
- AC-11.6 Determining policy ids (from `@id` or file order) are reported.
- AC-11.7 Without the extra installed, `--engine cedar` prints the install
  command and exits 1.

**FR-12 Python callable evaluator** (v0.1)
- AC-12.1 `--engine python:module.path:callable`; signature
  `(call: ToolCall, policy_dir: Path) -> Decision | str`; a string is
  coerced (`allow|deny|require_approval`).
- AC-12.2 Exceptions become `error/eval_error` with the exception text; one
  failing call does not abort the run.
- AC-12.3 `--verify-deterministic` runs the corpus twice and reports any
  differing decisions as `error/nondeterministic`.
- AC-12.4 Docs warn that this executes arbitrary code from the current
  environment.

### Replay and classification

**FR-13 Replay** (v0.1)
- AC-13.1 Every imported call yields exactly one base decision and one head
  decision; the footer reports imported, filtered, evaluated, and errored
  counts that sum correctly (tested).
- AC-13.2 Evaluation of base and head can run concurrently (two subprocesses
  for OPA).

**FR-14 Transition classification** (v0.1)
- AC-14.1 Classes and ordering per overview §3.3 with a table-driven test
  covering all 16 (effect × effect) combinations plus error cases.
- AC-14.2 Attribution changes (same effect, different determining policies)
  are a distinct class shown only with `--show-attribution` or in JSON.

**FR-15 Recorded-decision sanity check** (v0.1)
- AC-15.1 When calls carry `recorded.effect`, the report notes how many base
  decisions disagree with the recorded effect, with a hint ("base ref may
  not be the deployed policy").
- AC-15.2 Recorded effects never influence classification.

### Reporting

**FR-16 Grouping and sampling** (v0.1)
- AC-16.1 Default group key `(class, tool.name)`; `--group-by` accepts
  `tool`, `resource.type`, `agent`, `principal`, `reason`, combinable.
- AC-16.2 `--samples N` (default 3) deterministic samples per group, sorted
  by call id.
- AC-16.3 Groups sorted: widening first, then by count descending.

**FR-17 Redaction** (v0.1)
- AC-17.1 Levels `safe` (default) and `none`. `safe`: argument and attr
  values → `<type:len>` placeholders, keys kept; principal id → `principal:`
  + first 8 hex of SHA-256 with a per-run salt printed in the header (so
  hashes are correlatable within a report, not across reports, unless
  `--salt` is fixed); tool, agent, resource type, reasons shown.
- AC-17.2 `--show-args k1,k2` reveals listed keys under `safe`.
- AC-17.3 `--pr-comment` (or the Action) refuses `--redact none` with exit 1.
- AC-17.4 Sentinel test: fixture corpus seeded with unique PII strings; every
  reporter's output is asserted not to contain them under `safe`.
- AC-17.5 Redaction is applied in one place (reporter input), covered by a
  test that all reporters share it.

**FR-18 Terminal reporter** (v0.1)
- AC-18.1 Summary block as in overview §0, colored when TTY, plain otherwise
  (`--no-color`, `NO_COLOR`).
- AC-18.2 Groups with samples follow; `--quiet` prints only the summary.

**FR-19 Markdown reporter** (v0.1)
- AC-19.1 Starts with `<!-- permdiff -->` marker and a header with refs and
  SHAs; summary table; one collapsible section per group.
- AC-19.2 Byte-identical output for identical inputs (fixed salt in CI).
- AC-19.3 Under 60 KB for the demo corpus; truncates groups beyond
  `--max-groups` with a note.

**FR-20 JSON reporter** (v0.1)
- AC-20.1 Versioned envelope (`"permdiff_report": "1"`) with header, summary
  counts, groups, samples, and optionally `--include-decisions` per-call
  decisions; JSON Schema shipped.

**FR-21 SARIF reporter** (v0.1)
- AC-21.1 SARIF 2.1.0; one rule per transition class; one result per group
  (not per call) with the count in the message; level `error` for widening,
  `warning` for tightening and can't-evaluate, `note` otherwise.
- AC-21.2 Every result has a `physicalLocation` on the policy path (file and
  line when attribution is known, else the policy dir's first file, line 1)
  and `logicalLocations` for tool and hashed principal.
- AC-21.3 `partialFingerprints.primaryLocationLineHash` stable per group.
- AC-21.4 Validates against the SARIF 2.1.0 JSON Schema in tests.

**FR-22 Exit codes and gates** (v0.1)
- AC-22.1 `0` no match; `2` `--fail-on` matched; `1` tool failure.
- AC-22.2 `--fail-on widen|any-change|cant-evaluate|none`, default `widen`.
- AC-22.3 `--allow-widening "reason"` returns 0 on widening and records the
  reason and the invoking user (from git config or `GITHUB_ACTOR`) in every
  report format.

### CLI, config, onboarding

**FR-23 Configuration** (v0.1)
- AC-23.1 `permdiff.toml` keys per overview §4.4; precedence flags > env
  (`PERMDIFF_<SECTION>_<KEY>`) > file > defaults.
- AC-23.2 `permdiff init` writes the file from provided flags, refuses to
  overwrite without `--force`.
- AC-23.3 Unknown keys are errors with the key name.

**FR-24 `permdiff demo`** (v0.1)
- AC-24.1 Ships a fixture repo (two Rego policy versions, 200-call corpus)
  inside the package; `permdiff demo` runs the diff offline (needs the `opa`
  binary; `demo --engine python` needs nothing) and shows one widening, one
  tightening, one approval group, and one can't-evaluate group.
- AC-24.2 `permdiff demo --format markdown` prints the comment users will see.

**FR-25 `permdiff check`** (v0.1)
- AC-25.1 Validates traces parse and both refs' policies compile; prints
  counts; exit 1 on failure. Used by the Action before `diff`.

**FR-26 GitHub Action** (v0.1, last epic)
- AC-26.1 Composite action at the repo root (`action.yml`); inputs: `traces`,
  `base`, `head`, `policy`, `engine`, `fail-on`, `sarif`, `version`,
  `config`.
- AC-26.2 Upserts one PR comment with the marker via `actions/github-script`;
  updates in place; no duplicate comments across runs (integration test with
  a mocked API).
- AC-26.3 On a read-only token (fork PR) writes the markdown to
  `$GITHUB_STEP_SUMMARY` and uploads JSON as an artifact instead of failing.
- AC-26.4 `sarif: true` writes a SARIF file and documents the
  `upload-sarif@v4` step; the action does not upload itself.
- AC-26.5 Exit code propagates so the check fails on widening.

**FR-27 Python API** (v0.1)
- AC-27.1 `permdiff.diff(traces, base, head, engine, ...) -> Report`,
  `permdiff.load_traces(paths, fmt) -> list[ToolCall]`, `ToolCall`,
  `Decision`, `Evaluator` are public, typed (`py.typed`), and covered by an
  example in the README.

### Later (not v0.1)

- FR-L1 Langfuse importer (observations `type == TOOL`, JSONL and Parquet).
- FR-L2 LangSmith importer (`run_type == "tool"`, JSONL and Parquet).
- FR-L3 Claude Code hook log importer (`PreToolUse` JSON).
- FR-L4 OPA decision-log importer (`input`, `result`, `nd_builtin_cache`).
- FR-L5 TOLAP purpose-binding evaluator.
- FR-L6 Custody evaluator (once Custody has an evaluator API).
- FR-L7 Line-level determining-rule attribution for OPA.
- FR-L8 Symbolic complement: attach a Cedar symcc counterexample when a
  widening has zero trace hits.
- FR-L9 Regorus backend as an optional faster OPA path.
- FR-L10 HTML report; `permdiff serve` local viewer.
- FR-L11 Trace recording helpers (`permdiff record` hooks).

## 5. Non-functional requirements

**NFR-P Performance** (confirmed 2026-09-25)
- NFR-P1 100,000 calls, one engine, both refs, diffed and reported in under
  60 s wall-clock on a 2023-class laptop (Apple M2 or equivalent), measured
  by a benchmark script in the repo and recorded in the README. Proposed
  budget: import ≤ 20 s, evaluation ≤ 10 s per ref (OPA measured 0.62 s),
  classify + report ≤ 10 s, headroom 10 s.
- NFR-P2 Peak memory under 1 GiB for 100K calls.
- NFR-P3 `permdiff demo` completes in under 5 s after the binary is cached.
- NFR-P4 The benchmark runs in CI on every PR and fails on a 50% regression.

**NFR-S Security**
- NFR-S1 Threat model per overview §3.10 is maintained in docs.
- NFR-S2 No shell string construction for subprocesses (lint rule +
  review).
- NFR-S3 `opa` binary pinned by version and SHA-256; download over HTTPS;
  mismatch aborts.
- NFR-S4 Redaction sentinel tests (AC-17.4) run on every PR.
- NFR-S5 Temp dirs 0700, cleaned on all exit paths.
- NFR-S6 No telemetry, no network calls except the OPA binary download.
- NFR-S7 Dependencies pinned with a lock file; `pip-audit` in CI.

**NFR-C Compatibility and supported versions**
- NFR-C1 Python 3.11, 3.12, 3.13, 3.14 (CI matrix). 3.11 floor for `tomllib`
  and `ExceptionGroup`.
- NFR-C2 macOS (arm64, x86_64) and Linux (x86_64, arm64) first-class;
  Windows best-effort (CI smoke test, OPA binary supported).
- NFR-C3 OPA 1.x; pinned default 1.21.0; `--opa-bin` for others; Rego v1
  syntax default, `--v0-compatible` passthrough.
- NFR-C4 `cedarpy` pinned `~=4.12`; Cedar language 4.x.
- NFR-C5 git ≥ 2.30.
- NFR-C6 OTel GenAI conventions as of semconv-genai `main` on 2026-09-25;
  the importer is versioned and documented as tracking a Development-status
  spec.

**NFR-D Dependency budget**
- NFR-D1 Runtime dependencies ≤ 5: proposed `click`, `rich`, `pydantic>=2`
  (schema validation and fast JSON), plus at most two more if needed. No
  `requests` (stdlib `urllib`), no `GitPython` (subprocess `git`).
- NFR-D2 Optional extras: `cedar` (`cedarpy`), later `parquet` (`pyarrow`).
- NFR-D3 Dev tooling: `uv`, `hatchling`, `pytest`, `pytest-cov`,
  `hypothesis`, `ruff`, `mypy --strict`, `pip-audit`.

**NFR-Q Quality**
- NFR-Q1 Tests written alongside code; ≥ 80% line coverage enforced in CI.
- NFR-Q2 `ruff` (lint + format) and `mypy --strict` clean.
- NFR-Q3 Golden tests: OPA and Cedar fixture corpora with expected
  transitions checked in.
- NFR-Q4 Every reporter has a snapshot test.
- NFR-Q5 README quickstart is executed in CI (doctest-style script).

**NFR-O Operability**
- NFR-O1 `--verbose` prints engine commands and timings; `--debug` keeps temp
  dirs and prints their paths.
- NFR-O2 Errors are actionable: every error message names the file, line,
  ref, or flag involved.

**NFR-L Licensing and distribution** (decided 2026-09-25)
- NFR-L1 Apache-2.0 (matches the ecosystem: OPA, Cedar, TOLAP,
  Custody's competitors) with `LICENSE` and SPDX headers.
- NFR-L2 Wheel and sdist built with `hatchling`; `py.typed`; no publishing
  by the agent (standing rule 5).

## 6. Public API and CLI surface

```
permdiff diff      [--base REF] [--head REF|WORKTREE] [--policy PATH]
                   [--engine opa|cedar|python:MOD:FN] [--decision PATH]
                   [--traces GLOB ...] [--from auto|permdiff|custody|otel]
                   [--since DUR|ISO] [--until ISO] [--tool G] [--agent G] [--principal G]
                   [--format terminal|markdown|json|sarif] [--output FILE]
                   [--fail-on widen|any-change|cant-evaluate|none]
                   [--allow-widening REASON]
                   [--redact safe|none] [--show-args K,...] [--samples N]
                   [--group-by tool,resource.type,agent,principal,reason]
                   [--show-attribution] [--include-decisions]
                   [--opa-bin PATH] [--nd-cache FILE] [--v0-compatible]
                   [--verify-deterministic] [--pr-comment] [--salt HEX]
                   [--strict] [--quiet] [--verbose] [--debug] [--no-color]
permdiff check     (same selection flags; validates, no diff)
permdiff convert   --from custody|otel FILE ... [-o OUT.jsonl]
permdiff init      [flags to persist] [--force]
permdiff demo      [--engine opa|python] [--format ...]
permdiff setup opa [--version V]
permdiff schema    [toolcall|decision|report]
permdiff --version
```

Python:

```python
from permdiff import ToolCall, Decision, Evaluator, Report, load_traces, diff

report: Report = diff(
    traces=load_traces(["traces/*.jsonl"]),
    base="origin/main",
    head="HEAD",
    policy="policy/",
    engine="opa",
    decision="data.agent.authz.decision",
)
report.transitions, report.summary, report.to_markdown(), report.to_json()
```

Entry point group `permdiff.evaluators` for third-party adapters; group
`permdiff.importers` for third-party importers.

## 7. v0.1 scope vs later

**v0.1 (installable, demoable, CI-usable):** FR-1, FR-2, FR-3, FR-4, FR-5, FR-6,
FR-7, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-15, FR-16, FR-17,
FR-18, FR-19, FR-20, FR-21, FR-22, FR-23, FR-24, FR-25, FR-26, FR-27.

**Later:** FR-L1 through FR-L11.

Ordering principle: the first shippable increment is FR-1, FR-2, FR-8, FR-9,
FR-12 (Python engine), FR-13, FR-14, FR-17, FR-18, FR-22, FR-24, which gives a
`pip install` + `permdiff demo` + real diff on JSONL with a Python callable
before any engine binary is involved. OPA follows, then reporters, then
Cedar and importers, then the Action.

## 8. Assumptions

- Users can produce a JSONL of tool calls or already have Custody/OTel data.
  v0.1 does not record.
- Policies live in the same repository as the workflow that runs permdiff.
  Cross-repo policies are later.
- One engine per run. Mixed-engine repos run permdiff twice.
- Cedar entities are static per ref (`entities.json`); dynamic entity stores
  are later.

## 9. Open questions

Blocking questions were answered on 2026-09-25 (see decisions.md):

- OPEN-1 Performance target: confirmed as NFR-P1 (60 s, budget as written).
- OPEN-2 License: Apache-2.0.
- OPEN-3 v0.1 importer set: JSONL + Custody + OTel `execute_tool` spans.

Non-blocking (decided here, revisit on feedback):

- Python floor 3.11 (NFR-C1).
- Runtime dependencies `click`, `rich`, `pydantic` (NFR-D1).
- GitHub Action lives in this repo at `action.yml`, referenced as
  `smhasan94/permdiff@v0`.
- Undefined OPA results default to `deny` with the choice printed
  (AC-10.8).
