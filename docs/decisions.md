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

**Decision.** Option 1. Custody repo is `/Users/sharukhhasan/code/custody`
(origin `smhasan94/custody`).

**Rationale.** Keeps Custody a first-class input without blocking on Custody
implementation. Cheap to build; fixtures make the spec drift visible when
real traces appear. Option 3 rejected: tight coupling hurts standalone
adoption.
