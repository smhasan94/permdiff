# permdiff: epics and stories

*Status tracker. Update the status of every epic and story as work proceeds
(todo / in progress / done / reviewed). Requirements in
[02-prd.md](02-prd.md). Plans in `docs/plans/epic-NN-<slug>.md`.*

Ordering: by dependency, then time-to-first-value. Epic 1 ends with something
`pip install`-able and demoable. Each story is sized for about one day.

| Epic | Title | Status |
|---|---|---|
| E1 | Foundation: installable package, JSONL, Python engine, terminal diff, demo | reviewed |
| E2 | OPA evaluator | reviewed |
| E3 | Reporting, grouping, config | todo |
| E4 | GitHub Action | todo |
| E5 | Importers: Custody, OTel, convert | todo |
| E6 | Cedar evaluator | todo |
| E7 | Performance, hardening, release preparation | todo |

---

## E1 — Foundation: installable package, JSONL, Python engine, terminal diff, demo

Goal: `pip install .` then `permdiff demo` prints a real transition report
using the Python callable engine, and `permdiff diff --engine python:... --base
REF --head REF --traces x.jsonl` works on a real repo. No OPA binary yet.

Satisfies: FR-1, FR-2, FR-8, FR-9, FR-12, FR-13, FR-14, FR-15, FR-17 (terminal
subset), FR-18, FR-22, FR-24, FR-27 (initial). NFR-C1, NFR-D, NFR-Q, NFR-L.

| # | Story | Status |
|---|---|---|
| E1-S1 | Package skeleton and tooling | done |
| E1-S2 | `ToolCall` and `Decision` models, JSON Schema | done |
| E1-S3 | permdiff JSONL importer | done |
| E1-S4 | Evaluator protocol and Python callable evaluator | done |
| E1-S5 | Git policy loading | done |
| E1-S6 | Replay and transition classification | done |
| E1-S7 | Redaction core | done |
| E1-S8 | Terminal reporter and exit codes | done |
| E1-S9 | `permdiff diff` CLI wiring | done |
| E1-S10 | `permdiff demo` and README quickstart | done |

**E1-S1 Package skeleton and tooling.** FR: none directly; NFR-C1, NFR-D,
NFR-Q, NFR-L. Deps: none.
AC: `pyproject.toml` (hatchling, name `permdiff`, Python ≥ 3.11, deps `click`,
`rich`, `pydantic>=2`, extra `cedar`); `uv.lock`; `LICENSE` Apache-2.0;
`ruff`, `mypy --strict`, `pytest` + `pytest-cov` (80% gate) configured; GitHub
Actions CI workflow running lint, types, tests on 3.11–3.14 on Linux and macOS;
`permdiff --version` works after `uv pip install -e .`; README with one-line
description and install placeholder.

**E1-S2 `ToolCall` and `Decision` models, JSON Schema.** FR-1, FR-9 (Decision
part). Deps: S1.
AC: AC-1.1, AC-1.2, AC-1.3, AC-1.4 (limits enforced at model level where
applicable); `Decision` with `effect` enum and `ErrorKind`; `permdiff schema
toolcall|decision` prints JSON Schema; schema files shipped in the wheel;
Hypothesis round-trip test (model → JSON → model).

**E1-S3 permdiff JSONL importer.** FR-2, FR-5 (permdiff branch only). Deps: S2.
AC: AC-2.1 (100K-line fixture parses under 20 s, timed test marked `slow`),
AC-2.2, AC-2.3; importer protocol defined (`Importer.detect(first_bytes)`,
`Importer.read(path) -> Iterator[ToolCall]`); registry with entry-point group
`permdiff.importers`.

**E1-S4 Evaluator protocol and Python callable evaluator.** FR-9, FR-12.
Deps: S2.
AC: AC-9.1, AC-9.2 (entry-point group `permdiff.evaluators`), AC-12.1,
AC-12.2, AC-12.3, AC-12.4 (docstring + README warning); fixture module with a
deliberately time-dependent rule used by later tests.

**E1-S5 Git policy loading.** FR-8. Deps: S1.
AC: AC-8.1 through AC-8.6; tests create a temp git repo with two commits and
verify extraction, WORKTREE mode, cleanup on exception, and rejection of
refs like `--upload-pack=...`.

**E1-S6 Replay and transition classification.** FR-13, FR-14, FR-15. Deps:
S4.
AC: AC-13.1 (counts sum, property test), AC-13.2 (base/head evaluated via a
thread pool; adapters may override), AC-14.1 (table-driven test over all
effect pairs and error kinds), AC-14.2, AC-15.1, AC-15.2.

**E1-S7 Redaction core.** FR-17 (all but `--pr-comment` refusal, which lands
in E3). Deps: S2.
AC: AC-17.1 (placeholders, salted principal hash), AC-17.2, AC-17.4 sentinel
fixture and test harness reusable by every reporter, AC-17.5 (single
`Redactor` applied to a `Report` before any reporter sees it).

**E1-S8 Terminal reporter and exit codes.** FR-18, FR-22. Deps: S6, S7.
AC: AC-18.1, AC-18.2, AC-22.1, AC-22.2, AC-22.3; snapshot test of the summary
block; sentinel test passes for terminal output.

**E1-S9 `permdiff diff` CLI wiring.** FR-27 (initial API), CLI surface for
the flags implemented so far. Deps: S3, S5, S8.
AC: `permdiff diff --engine python:mod:fn --policy P --base A --head B
--traces G` runs end to end on the temp git repo fixture; `permdiff.diff()`
and `permdiff.load_traces()` public and typed; `--verbose` timings;
`--debug` keeps temp dirs; errors name file/line/ref/flag (NFR-O2).

**E1-S10 `permdiff demo` and README quickstart.** FR-24 (Python engine
variant). Deps: S9.
AC: bundled fixture (two policy dirs implemented as Python rule tables, 200-call
corpus with sentinel-free synthetic data) showing widening, tightening,
approval, can't-evaluate; `permdiff demo` runs offline in under 5 s; README
quickstart section executed by a CI script (NFR-Q5); epic marked done only
when `pip install .` from a clean venv followed by `permdiff demo` works.

---

## E2 — OPA evaluator

Goal: `permdiff diff --engine opa` works against real Rego policies at two git
refs, 100K calls per ref in seconds, with time injection and fail-closed
nondeterminism.

Satisfies: FR-10, FR-25, NFR-C3, NFR-S3.

| # | Story | Status |
|---|---|---|
| E2-S1 | OPA binary management and `permdiff setup opa` | done |
| E2-S2 | Batch evaluation shim and result mapping | done |
| E2-S3 | Time injection, capabilities restriction, nd-cache | done |
| E2-S4 | `permdiff check` and demo on OPA | done |

**E2-S1 OPA binary management.** FR-10 (AC-10.1), NFR-S3. Deps: E1.
AC: pinned version and per-platform SHA-256 table in package; download to user
cache over HTTPS with checksum verification; `--opa-bin` / `PERMDIFF_OPA_BIN`;
`permdiff setup opa [--version]`; offline failure message names the flag;
tests mock the download.

**E2-S2 Batch evaluation shim and result mapping.** AC-10.2, AC-10.3,
AC-10.4, AC-10.8, AC-10.9, AC-10.10. Deps: S1.
AC: generated `permdiff_shim.rego` + `cases.json` per ref; one `opa eval`
process; results joined by call id; object and boolean mappings; unknown
effects → `error/unsupported`; undefined → configured default with header
note; 100K-case timed test under 10 s per ref (`slow`); `--v0-compatible`.

**E2-S3 Time injection, capabilities, nd-cache.** AC-10.5, AC-10.6, AC-10.7.
Deps: S2.
AC: `with time.now_ns as c.ts_ns` per case; business-hours fixture flips;
default capabilities file omits network/random builtins; policy using
`http.send` yields `error/nondeterministic` naming the builtin for all calls;
`--nd-cache` re-enables with recorded values and missing entries are errors.

**E2-S4 `permdiff check` and demo on OPA.** FR-25, FR-24 (OPA variant). Deps:
S3.
AC: `permdiff check` validates traces and compiles both refs; `permdiff demo`
defaults to OPA when the binary is available and falls back to Python with a
note; README quickstart updated for OPA; golden corpus with expected
transitions committed (NFR-Q3).

---

## E3 — Reporting, grouping, config

Goal: PR-ready markdown, machine-readable JSON, SARIF, grouping and sampling,
`permdiff.toml`, trace filters.

Satisfies: FR-6, FR-16, FR-17 (completion), FR-19, FR-20, FR-21, FR-23.

| # | Story | Status |
|---|---|---|
| E3-S1 | Grouping and sampling | todo |
| E3-S2 | Markdown reporter | todo |
| E3-S3 | JSON reporter and report schema | todo |
| E3-S4 | SARIF reporter | todo |
| E3-S5 | Config file, env, `permdiff init` | todo |
| E3-S6 | Trace filters | todo |

**E3-S1 Grouping and sampling.** FR-16. Deps: E1.
AC: AC-16.1, AC-16.2, AC-16.3; terminal reporter uses groups.

**E3-S2 Markdown reporter.** FR-19, AC-17.3. Deps: S1.
AC: AC-19.1, AC-19.2 (fixed salt test), AC-19.3; `--pr-comment` refuses
`--redact none`; sentinel test; snapshot test.

**E3-S3 JSON reporter.** FR-20. Deps: S1.
AC: AC-20.1; JSON Schema shipped and validated in tests; `--include-decisions`;
sentinel test.

**E3-S4 SARIF reporter.** FR-21. Deps: S1.
AC: AC-21.1 through AC-21.4 (schema validation test); sentinel test.

**E3-S5 Config file, env, `permdiff init`.** FR-23. Deps: E1-S9.
AC: AC-23.1, AC-23.2, AC-23.3; precedence test matrix.

**E3-S6 Trace filters.** FR-6. Deps: E1-S3.
AC: AC-6.1, AC-6.2; footer counts.

---

## E4 — GitHub Action

Goal: a repo adds one workflow step and gets a sticky PR comment and a failing
check on widening.

Satisfies: FR-26.

| # | Story | Status |
|---|---|---|
| E4-S1 | Composite action and comment upsert | todo |
| E4-S2 | Fork fallback, SARIF option, docs | todo |

**E4-S1 Composite action and comment upsert.** AC-26.1, AC-26.2, AC-26.5.
Deps: E3.
AC: `action.yml` at repo root; setup-python, pinned install, `permdiff check`
then `diff --format json`, markdown rendered from JSON, upsert via
`actions/github-script` with the marker; exit code propagates; the repo
dogfoods the action on its own demo fixture in CI.

**E4-S2 Fork fallback, SARIF option, docs.** AC-26.3, AC-26.4. Deps: S1.
AC: read-only token path writes `$GITHUB_STEP_SUMMARY` and uploads artifact;
`sarif: true` writes file and README documents `upload-sarif@v4`; README
integration section complete.

---

## E5 — Importers: Custody, OTel, convert

Goal: real-world trace sources work without hand conversion.

Satisfies: FR-3, FR-4, FR-5 (auto-detect), FR-7.

| # | Story | Status |
|---|---|---|
| E5-S1 | Custody importer | todo |
| E5-S2 | OTel importer: OTLP JSON and JSONL, `execute_tool` spans | todo |
| E5-S3 | OTel parent-span argument fallback and aliases | todo |
| E5-S4 | Auto-detection and `permdiff convert` | todo |

**E5-S1 Custody importer.** FR-3. Deps: E1-S3.
AC: AC-3.1 through AC-3.4; fixtures for every `action.type` and every
`decision.verdict`; digest-only fixture.

**E5-S2 OTel importer core.** AC-4.1, AC-4.2, AC-4.5. Deps: E1-S3.
AC: parses `resourSpans → scopeSpans → spans` in both OTLP/JSON and JSONL;
typed `AnyValue` decoding (string, int-as-string, kvlist, array); fixtures
generated from the semconv examples; `--principal-from`.

**E5-S3 OTel fallback and aliases.** AC-4.3, AC-4.4. Deps: S2.
AC: parent chat span `gen_ai.output.messages` `tool_call` lookup by id;
deprecated attribute aliases; MCP `tools/call` spans.

**E5-S4 Auto-detection and convert.** FR-5, FR-7. Deps: S1, S3.
AC: AC-5.1, AC-5.2, AC-7.1 (round-trip test).

---

## E6 — Cedar evaluator

Goal: `pip install permdiff[cedar]` and `--engine cedar` work with schema
validation, request templates, and annotation-based approval.

Satisfies: FR-11, NFR-C4.

| # | Story | Status |
|---|---|---|
| E6-S1 | Cedar policy loading, templates, batch evaluation | todo |
| E6-S2 | Approval annotation, errors, attribution, golden corpus | todo |

**E6-S1 Cedar loading and evaluation.** AC-11.1, AC-11.2, AC-11.3, AC-11.7.
Deps: E1.
AC: extra installs `cedarpy~=4.12`; policy dir conventions; templates from
config; `context.now`; `is_authorized_batch`; timed test recorded in README.

**E6-S2 Approval, errors, attribution, golden corpus.** AC-11.4, AC-11.5,
AC-11.6. Deps: S1.
AC: `@require_approval` mapping incl. mixed forbid case; missing
entity/attribute → `error/missing_context` with name; determining policy ids;
golden Cedar corpus with expected transitions (NFR-Q3); demo gains a Cedar
variant.

---

## E7 — Performance, hardening, release preparation

Goal: NFR-P met and enforced; security NFRs verified; package ready for the
owner to publish (no publishing by the agent).

Satisfies: NFR-P1–P4, NFR-S2, NFR-S5, NFR-S7, NFR-Q5, NFR-L2.

| # | Story | Status |
|---|---|---|
| E7-S1 | Benchmark script and CI regression gate | todo |
| E7-S2 | Security hardening pass | todo |
| E7-S3 | Release preparation | todo |

**E7-S1 Benchmark.** NFR-P1–P4. Deps: E2, E3.
AC: `bench/` script generating 100K synthetic calls; runs OPA and Python
engines end to end; records numbers in README; CI job fails on 50%
regression against a checked-in baseline.

**E7-S2 Security hardening.** NFR-S2, NFR-S5, NFR-S7. Deps: E4, E5, E6.
AC: ruff rule banning `shell=True`; temp-dir permission tests; `pip-audit`
in CI; threat-model doc updated with anything learned; security-review
checklist from CLAUDE rules run and findings fixed.

**E7-S3 Release preparation.** NFR-L2. Deps: S1, S2.
AC: `CHANGELOG.md`; version `0.1.0`; wheel and sdist build clean;
`twine check` passes; Action tag plan (`v0`, `v0.1.0`) documented; README
final; halt and hand to owner for publishing.
