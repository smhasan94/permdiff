# permdiff

A "terraform plan" for AI agent permission changes. Replays recorded agent
tool-call **decisions** (not LLM behavior) against a policy at two git refs
and reports allow/deny/require-approval transitions. No models involved.

```
permdiff diff --base origin/main --head HEAD --traces traces/*.jsonl
```

Transitions reported: allow→deny (tightening), deny→allow (widening, always
flagged), anything→require-approval, and "can't evaluate" (missing context,
never silently treated as allow). Output: terminal summary, markdown PR
comment, JSON, SARIF. Exit codes let CI fail on unapproved widening.

Priority: time-to-first-value. Small, excellent, `pip install`-able v0.1 that
delivers value within five minutes of reading the README, no infrastructure
for the core use case. Fewer features done well over breadth.

## Standing rules (every phase, every session)

1. **Halt on questions and gaps.** STOP and ask before continuing whenever
   anything is ambiguous, missing, or contradictory, or when something learned
   changes the plan (upstream project already does part of this, an API
   differs from assumptions, requirements conflict). Every halt includes:
   the question and why it matters; a recommended approach with reasoning;
   one to three alternatives with trade-offs. Wait for the answer. Never
   guess and continue. Record each answer in `docs/decisions.md` (date,
   question, options, decision, rationale), then commit and push.
2. **Git.** Work on `main` only. No branches, no PRs. Small logical commits
   (one story or less), push to `origin main` after every commit. Message:
   short imperative summary line plus optional body. NEVER include:
   a `Co-Authored-By` trailer, a "Generated with Claude Code" line, a session
   link, or any other AI attribution. `.git/hooks/commit-msg` strips these as
   a safety net (reinstall it if `.git` is recreated; see Phase 0 below).
3. **Verify before relying.** Facts in the original brief were accurate as of
   2026-09-25. Check every external library, spec, API, or file format against
   current docs or source before building on it. If reality differs in a way
   that matters, halt (rule 1).
4. **Tests gate commits.** Write tests alongside code. Run test suite, linter,
   and type checker before each commit. Never commit red.
5. **Don't publish.** Never publish packages (PyPI/npm), create releases or
   tags, post to external sites, or change repository settings. Prepare
   everything, then halt and hand it over.
6. **Track progress in the repo.** Keep the status of every epic and story
   current in `docs/03-epics.md` (todo / in progress / done / reviewed) so work
   resumes cleanly after a context reset.

## Decisions expected to need the owner (halt when each comes up)

- **Name.** Decided: `permdiff` (see docs/decisions.md).
- **v0.1 engines.** Which policy engines make v0.1.
- **Require-approval modeling.** Generic or per engine.
- **Nondeterministic policies.** Policies that do external data lookups.
- **Redaction default.** Default redaction policy for samples in reports.
- **Custody repo path.** Asked during Phase 0; Custody trace format is a
  first-class input.
- **Performance target.** 100K calls under a minute on a laptop; confirm in
  Phase 2.

## Phase sequence (strictly in order; a phase starts only after the previous
## one is committed and pushed)

- **Phase 0: Setup.** Confirm git repo on `main` with pushable `origin`.
  Install `.git/hooks/commit-msg` (executable) that strips attribution lines.
  Write this CLAUDE.md. First commit + push. Verify `git log -1 --format=%B`
  has no attribution.
- **Phase 1: Overview → `docs/01-overview.md`.** Research current landscape
  (Cedar analysis tooling, OPA tooling, commercial agent-security products,
  agent replay tools: pytest-agentreplay, TraceOps, agentpytest, Reflight,
  plus anything else). Halt if something already solves this well. Write:
  problem + worked example; existing solutions and gaps with links; how it
  works (architecture, components, data flow, design decisions and rejected
  alternatives, trust boundaries / threat model); how developers use it
  (install, five-minute quickstart, integration examples, configuration);
  non-goals; success signals.
- **Phase 2: PRD → `docs/02-prd.md`.** Goals/non-goals, personas, numbered
  FR-N with acceptance criteria, NFRs (performance, security, compatibility
  and supported versions, dependency budget), public API/CLI surface, v0.1
  scope vs later, open questions. Halt on any open question blocking v0.1.
- **Phase 3: Epics → `docs/03-epics.md`.** Group FRs into epics; stories of
  about a day each with acceptance criteria, FR IDs, dependencies. Order by
  dependency and time-to-first-value; first epic ends installable + demoable.
- **Phase 4: Plans → `docs/plans/epic-NN-<slug>.md`.** Use the `plan` skill
  per epic, in order, before any code: files, interfaces, test strategy,
  sequencing, risks. Halt if no `plan` skill.
- **Phase 5: Implementation.** Epic by epic, story by story, per plans.
  Re-read and update each epic's plan before starting it (commit update).
  Commit + push after each story or smaller. README quickstart works at every
  step.
- **Phase 6: Review.** After each epic: code-review in low mode on that epic's
  changes. Fix issues, rerun tests, commit, push. Mark epic "reviewed" in
  `docs/03-epics.md`. Return to Phase 5 for next epic. Halt if code-review
  unavailable.

## Scope reference

- **Schema + importers:** canonical decision-input schema (principal, agent,
  tool, arguments, resource, context attributes, timestamp). Importers: JSONL
  (v0.1), OpenTelemetry GenAI tool-call spans (verify current semconv),
  Custody traces, Langfuse/LangSmith exports (later).
- **Evaluator interface:** pluggable; v0.1 adapters for Cedar and OPA/Rego
  plus plain Python callable (verify current Python bindings or use
  subprocess). TOLAP action validation and Custody as later adapters.
- **Git-aware policy loading** from refs.
- **Grouping/sampling** by tool, resource, agent; argument redaction. Traces
  contain PII; PR comment must never leak it.
- **GitHub Action** posting/updating a single PR comment.
- **Performance:** 100K calls < 1 min on a laptop (confirm Phase 2).
