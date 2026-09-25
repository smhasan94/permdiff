# Decisions

Record of every halt-and-ask decision. Newest at the bottom.

Format per entry: date, question, options considered, decision, rationale.

---

## 2026-09-25 — Custody repo path and trace-format source

**Question.** Where is the Custody repo, and what do we build the Custody
importer against, given the repo is planning docs only (no code, no emitted
traces yet)?

**Options.**
1. Treat `custody/PLAN.md` §5 (`custody.trace.v1` JSONC sketch) as the spec.
   Build the importer against it with fixture files; document it as
   spec-derived and unverified against real output.
2. Defer the Custody importer until Custody emits real traces.
3. Adopt `custody.trace.v1` as policyplan's canonical schema.

**Decision.** Option 1. Custody repo is the local clone of
`github.com/smhasan94/custody`.

**Rationale.** Keeps Custody a first-class input without blocking on Custody
implementation. Cheap to build; fixtures make the spec drift visible when
real traces appear. Option 3 rejected: tight coupling hurts standalone
adoption.

## 2026-09-25 — Project name

**Question.** Working name was `policyplan`; repo is `permdiff`. Which name ships?
Collision check (PyPI, npm, crates.io, Homebrew, GitHub, `.dev`/`.io`) done
2026-09-25.

**Options.**
1. `permdiff`: clear on every registry and domain; only neighbors are
   `permadiff` (Terraform noise filter) and MATLAB `permdiff.m`.
2. `policyplan`: clear everywhere; carries the terraform-plan analogy; but
   "policy plan" is insurance jargon and RL "policy planning" literature.
3. `policyreplay`: clear; names the mechanism, hides the diff output.
   Rejected outright: `policydiff` (npm taken, three active projects),
   `authzdiff` (`MEZ111/authz-diff` exists).

**Decision.** Option 1, `permdiff`. Package `permdiff`, CLI `permdiff`,
module `permdiff`.

**Rationale.** Says what it does (permission transitions), short, typeable,
matches the repo, no collisions. Trademark search (USPTO) not run.

## 2026-09-25 — v0.1 policy engines

**Question.** Which engines make v0.1?

**Options.**
1. OPA + Cedar + Python callable; Cedar as optional extra.
2. OPA + Python callable only; Cedar in v0.2.
3. Cedar + Python callable only.

**Decision.** Option 1. OPA via a pinned `opa` binary subprocess with
one-process batch evaluation (measured 100K inputs in 0.62 s on OPA 1.21.0).
Cedar via `cedarpy` (4.12.1, `is_authorized_batch`) behind
`pip install permdiff[cedar]`. Python callable built in.

**Rationale.** Matches the brief's v0.1 scope. Regorus is not on PyPI, so the
binary is the only maintained fast path for OPA. `cedarpy` is third-party and
lags the Cedar crate by about one minor version, hence optional extra.

## 2026-09-25 — Require-approval modeling

**Question.** Model "require approval" generically or per engine?

**Options.**
1. Generic tri-state in the canonical Decision (`allow | deny |
   require_approval`, plus an `error` bucket); per-engine adapters map into
   it.
2. Per engine only.
3. Binary allow/deny in v0.1.

**Decision.** Option 1. OPA: configurable result mapping, default
`{"effect": ..., "reason": ...}`, fallback to boolean `allow`. Cedar: only
Allow/Deny exist; `require_approval` is a Deny whose determining policies all
carry a configurable annotation (default `@require_approval`), the same
pattern sbproxy uses. Python callable returns the Decision directly.

**Rationale.** Reports stay uniform across engines; the brief's example
summary needs a "now REQUIRE_APPROVAL" row.

## 2026-09-25 — Nondeterministic policies

**Question.** How to handle policies that do external lookups or read the
clock?

**Options.**
1. Fail closed into the "can't evaluate" bucket. Time always injected from
   the trace timestamp. Static scan for nondeterministic builtins; run OPA
   with restricted capabilities. Affected calls are "can't evaluate" unless
   the user supplies recorded values (OPA `nd_builtin_cache` or a stub
   fixture file). Never run live lookups.
2. Allow live lookups behind a flag.
3. Hard error on any nondeterministic builtin.

**Decision.** Option 1.

**Rationale.** Reproducible PR comments; a call is never silently treated as
allow. Option 3 would block users with one unrelated `http.send` rule.

## 2026-09-25 — Redaction default

**Question.** Default redaction for sample calls in reports.

**Options.**
1. "safe": argument values replaced by type+length placeholders, keys kept;
   tool/resource/agent names shown; principal shown in terminal, replaced by
   a stable short hash in markdown/JSON/SARIF; grouping on hashed values;
   `--show-args` allowlist and `--redact none` opt in for local use; PR
   comment mode refuses `--redact none`.
2. Digest only (no keys).
3. Full args by default.

**Decision.** Option 1.

**Rationale.** Traces contain PII; one misconfigured Action must not leak it
into a PR. Keys without values still make diffs readable.

## 2026-09-25 — Performance target

**Question.** Confirm NFR-P1: 100K calls, both refs, diffed and reported in
under 60 s wall-clock on an M2-class laptop, with budget import ≤ 20 s,
evaluation ≤ 10 s per ref, classify + report ≤ 10 s, 10 s headroom.

**Options.** 60 s as written; 30 s (forces msgspec and early tuning); 120 s
(no engineering benefit).

**Decision.** 60 s as written.

**Rationale.** OPA batch evaluation measures 0.62 s per ref, so the target is
comfortable and leaves room for pydantic parsing.

## 2026-09-25 — License

**Question.** The brief did not specify a license.

**Options.** Apache-2.0; MIT; MPL-2.0.

**Decision.** Apache-2.0.

**Rationale.** Patent grant; matches OPA, Cedar, TOLAP, and the surrounding
ecosystem.

## 2026-09-25 — v0.1 importer set

**Question.** Brief marks JSONL as v0.1 and Langfuse/LangSmith as later; OTel
and Custody ambiguous.

**Options.**
1. JSONL + Custody + OTel `execute_tool` spans.
2. JSONL + Custody; OTel in v0.2.
3. JSONL only.

**Decision.** Option 1.

**Rationale.** OTel is the only vendor-neutral source; Custody importer is
cheap and spec-derived. Costs roughly two days before the Action ships.

## 2026-09-25: verifying the GitHub Action's sticky comment (open, needs owner)

**Question.** E4 acceptance asks for a dogfood pull request showing one comment that
updates in place. Standing rule 2 forbids the agent from creating branches or PRs.

**Options.**
1. Owner opens a throwaway PR against this repository after handover and confirms the
   comment appears once and updates on a second push (recommended: zero rule changes;
   the upsert logic is unit-tested against a mocked octokit and the summary path runs on
   every push to `main` via `.github/workflows/dogfood.yml`).
2. Owner grants a one-time exception for the agent to open and close a verification PR.
3. Accept the unit test plus the push-triggered dogfood run as sufficient.

**Decision.** Resolved 2026-09-25 via option 2 in spirit: the owner opened PR #1
(`verify-comment`, a docstring-only change to the demo head policy) and asked the agent to
verify. Observed: exactly one `<!-- permdiff -->` comment, updated in place on each push
(`updated_at` advanced, `base` SHA in the body changed), all 11 checks green (8 test cells,
quickstart, bench, dogfood). The branch is a throwaway; close PR #1 without merging.
