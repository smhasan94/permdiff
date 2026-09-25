# permdiff: project overview

*Status: Phase 1 deliverable. Research verified 2026-09-25. Decisions referenced
here are recorded in [decisions.md](decisions.md).*

permdiff is `terraform plan` for AI-agent permission changes. It replays a corpus
of recorded agent tool calls against an authorization policy at two git refs and
reports which calls change decision: what becomes denied, what becomes allowed,
what now needs human approval, and what could not be evaluated. It never calls a
model. It replays **decisions**, not behavior.

```
$ permdiff diff --base origin/main --head HEAD --traces traces/*.jsonl

permdiff: origin/main → HEAD   (4,812 calls, 2026-09-18 → 2026-09-25)
  newly DENIED             37   aws.ec2.terminate_instance
  newly ALLOWED             2   github.delete_branch          ⚠ widening
  now REQUIRE_APPROVAL    118   stripe.refund  amount>500
  can't evaluate            9   missing context: principal.department
  unchanged             4,646

exit 2 (widening found; --fail-on widen)
```

---

## 1. The problem

### Who has it

Teams that put an authorization policy between an AI agent and its tools. The
policy decides, per call, whether `stripe.refund(amount=750)` from agent
`support-bot` acting for `alice@example.com` is allowed, denied, or held for a
human. The policy is code: Cedar, OPA/Rego, a YAML rules file compiled by a
gateway, a Python function, or a control plane such as Custody. It lives in
git. It changes in pull requests.

The people who own that policy are platform, security, and AI-infrastructure
engineers. They review policy PRs the way they review any code: read the diff,
run the unit tests, merge.

### What goes wrong today

A policy diff tells you what the *text* changed. It does not tell you what the
*decisions* change on the traffic you actually have.

- **Unit tests encode the author's intent.** If the author misunderstood the
  traffic, the tests pass and the policy is still wrong. Policy tests are also
  usually sparse: a handful of hand-written requests against a policy that sees
  thousands of distinct tool/argument/principal combinations per day.
- **Widening is invisible.** Removing a `not`, loosening a glob from
  `github.repos.*` to `github.*`, or reordering `forbid` and `permit` blocks
  can grant an agent a destructive capability. The diff looks like a
  refactor. Nothing in the review process asks "which recorded calls that were
  denied last week would now be allowed?"
- **Tightening breaks agents in production.** A stricter rule that looks
  harmless denies a tool the agent relies on. The failure appears as agent
  behavior ("the bot stopped resolving tickets"), hours later, and gets
  debugged as a model problem.
- **Context-dependent policies are hard to reason about.** Time windows,
  department attributes, environment flags, and resource tags interact. A
  reviewer cannot mentally evaluate a Rego rule with four conjuncts across
  5,000 real requests.
- **Symbolic tools answer a different question.** Cedar's symbolic analysis
  can prove policy B is more permissive than policy A *somewhere* in the
  request space. It cannot tell you whether that somewhere is a call your
  agents make, how often, or for whom.

### A concrete worked example

A support agent (`support-bot`) has three tools that matter:
`stripe.refund`, `github.delete_branch`, and `aws.ec2.terminate_instance`. Its
authorization policy is Rego, in `policy/agent.rego`, reviewed in PRs.

PR-212 intends one change: refunds over 500 must be held for human approval.
The author also "cleans up" a nearby rule. The intended diff:

```rego
-allow if { input.tool.name == "stripe.refund" }
+decision := {"effect": "require_approval", "reason": "refund > 500"} if {
+  input.tool.name == "stripe.refund"
+  input.arguments.amount > 500
+}
```

The cleanup:

```rego
-deny if { input.tool.name == "github.delete_branch"; not input.principal.attrs.release_manager }
+deny if { input.tool.name == "github.delete_branch"; input.principal.attrs.release_manager == false }
```

The second change looks equivalent. It is not: most principals do not have a
`release_manager` attribute at all, so `== false` is undefined and the `deny`
rule never fires for them. Every non-release-manager who was denied
`github.delete_branch` last week is now allowed.

The unit tests pass. They were written with a fixture principal that has
`release_manager: false`. The reviewer approves. Two days later an agent
deletes a release branch.

With permdiff in CI, PR-212 gets this comment before anyone reads the diff:

| transition | calls | tool | note |
|---|---:|---|---|
| allow → require_approval | 118 | `stripe.refund` | intended |
| **deny → allow** | **2** | `github.delete_branch` | **widening** |
| can't evaluate | 9 | `aws.ec2.terminate_instance` | missing `principal.department` |

The check fails on the widening. The author sees two recorded calls (arguments
redacted, principals hashed) that would now be allowed, understands the
`undefined` trap, and fixes the rule. The 118 approvals confirm the intended
change did what it should. The 9 "can't evaluate" rows point at a trace source
that does not record department, which is a separate, visible problem rather
than a silent allow.

---

## 2. Existing solutions and where they fall short

Research across the Cedar and OPA ecosystems, authorization-as-a-service
vendors, AI-agent security products, agent replay tools, and cloud IAM tooling
found no tool that replays recorded agent tool calls against a policy at two git
refs and reports decision transitions. The idea itself has precedent in adjacent
domains, and three independent 2026 efforts circle it. Details:

### Closest prior art (replays real decisions)

| Project | What it does | Where it falls short for this problem |
|---|---|---|
| [Permit.io `permit test run audit`](https://docs.permit.io/how-to/use-audit-logs/audit-log-replay/) | Re-runs Permit's own audit logs (6–72 h window) against a PDP and flags mismatches | Only Permit's logs, only if every tool call already routes through Permit; needs a live PDP; compares log vs one PDP, not ref vs ref; boolean allow/deny; no agent tool/argument model |
| Styra DAS Log Replay / [Enterprise OPA Live Impact Analysis](https://github.com/open-policy-agent/eopa) | Replayed decision-log inputs (DAS) or sampled live traffic (EOPA) against a draft bundle and reported changed decisions | Styra wound down in Aug 2025 ([note from the maintainers](https://www.openpolicyagent.org/blog/note-from-teemu-tim-and-torin-to-the-open-policy-agent-community-2dbbfe494371)); DAS docs no longer resolve; EOPA repo archived 2026-06-26; both compared deployed vs draft, not git refs; server-side, not an offline CLI |
| [Google IAM Policy Simulator](https://docs.cloud.google.com/policy-intelligence/docs/iam-simulator-overview) | Replays 90 days of access logs against a proposed IAM allow policy; reports access gained/revoked/unknown | Cloud IAM only; 5,000-log cap; no conditions; the exact concept, wrong domain |
| [sbproxy `cedar replay`](https://github.com/soapbucket/sbproxy/tree/main/examples/cedar-replay) | Evaluates JSONL samples against baseline and proposed Cedar evaluators, prints changed verdicts, exit 0/1/2 | Samples carry no context or entities (empty Cedar context), action defaults to one MCP action, policies come from sbproxy's own YAML, no git-ref support |
| [clay-good/agent-replay](https://github.com/clay-good/agent-replay) | SQLite store of agent runs; `guard test <trace-id>` shows what a deny/require_review/warn guard would have done on a recorded trace | One trace at a time; no corpus summary; no policy-version comparison; pattern rules on step names, not a principal/resource model |
| [hsskey/authority-diff](https://github.com/hsskey/authority-diff) (created 2026-09-21) | Imports Claude Code transcripts, evaluates them under policy versions, shows allow/ask/deny widening and narrowing groups | Own JSON policy DSL only (no Cedar/OPA); Claude Code transcripts only; Postgres + web app, no CLI/CI path; no git refs |
| [Invariant Guardrails](https://github.com/invariantlabs-ai/invariant) | `LocalPolicy.analyze(trace)` runs a trace-model policy offline over a stored trace | Own policy language; no two-version diff; Snyk-owned |
| [`p0nymc1/cee` policydiff](https://pkg.go.dev/github.com/p0nymc1/cee/policydiff) | "Which decisions come out differently when running historical inputs through two manifests" | Internal to CEE's Go workflow-manifest engine, not an authorization engine |
| [bernstein #5066](https://github.com/sipyourdrink-ltd/bernstein/issues/5066) (2026-09-01) | Proposes `replay_decisions(corpus, policy) -> DecisionDiff` with ALLOW→DENY / DENY→ALLOW counts | Open issue, not implemented |

### Symbolic policy analysis (no traces)

- [Cedar symbolic analysis](https://github.com/cedar-policy/cedar/tree/main/cedar-policy-symcc)
  (`cedar-policy-symcc` 0.7.0) and the
  [Cedar Analysis CLI](https://github.com/cedar-policy/cedar-spec/blob/main/cedar-lean-cli/README.md)
  (`analyze compare pset1 pset2`) prove equivalence, subsumption, and
  disjointness over the whole request space via SMT, with synthesized
  counterexamples. Needs cvc5 and a Lean toolchain. Answers "could anything
  change?", not "what recorded calls change?". Complementary: a future permdiff
  mode could attach a synthesized counterexample when no trace exercises a
  widening.
- [AWS IAM Access Analyzer custom policy checks](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-custom-policy-checks.html)
  (`CheckNoNewAccess`) do the same for IAM.
- [Amazon Verified Permissions test bench](https://docs.aws.amazon.com/verifiedpermissions/latest/userguide/test-bench.html)
  simulates one request at a time.

### Policy testing without replay

[Cerbos `compile` tests](https://docs.cerbos.dev/cerbos/latest/policies/compile.html),
[OpenFGA model tests](https://openfga.dev/docs/modeling/testing), SpiceDB `zed
validate`, Oso `oso-cloud test`, `opa test`, and the
[Regal](https://github.com/open-policy-agent/regal) linter all test a policy
against hand-written cases. None consume recorded traffic.

### Agent replay tools (replay the model, not the policy)

[pytest-agentreplay](https://github.com/aafre/agentreplay) records and replays
model and tool I/O as cassettes for deterministic tests.
[agentpytest](https://github.com/piyushbhavsarr/agentpytest) is a placeholder
("record, score, replay, regress"). [Reflight](https://www.reflight.dev/) does
pre-deploy agent simulations. "TraceOps" has no canonical project. None
evaluate an authorization policy.

### Runtime enforcement products (no historical replay)

[Microsoft Agent Governance Toolkit](https://github.com/microsoft/agent-governance-toolkit)
(YAML/Cedar/OPA policy, allow/deny/require_approval, audit-only mode),
PolicyLayer Intercept (shadow mode on live traffic), Runlayer, Okta Agent
Gateway, NVIDIA OpenShell, agentjail, Lakera, Zenity, Noma, and the AI-gateway
class (LiteLLM, Portkey, Kong) enforce at runtime. Several have a shadow or
audit-only mode for *live* traffic. None replay *historical* calls against a
*proposed* policy. Static config diffs of agent settings exist
([saagpatel/agent-permission-diff-bot](https://github.com/saagpatel/agent-permission-diff-bot)
takes `--base-ref/--head-ref`) but diff files, not decisions.

### Conclusion

The primitive is recognized as missing. The DEMM-Bench paper notes "the closest
commercial precedent is authorization replay [Styra, Permit.io] ... neither
targets an agent runtime decision." The two shipping products that did
authorization replay are dead (Styra) or closed to their own logs (Permit.io).
The agent-native attempts are single-trace, single-DSL, or issues. permdiff is
the engine-agnostic, git-native, offline, CI-first version of this idea.

---

## 3. How permdiff works

### 3.1 Architecture

```
 traces/*.jsonl ─┐
 otel spans ─────┤   ┌──────────┐    ┌───────────────┐    ┌───────────┐
 custody traces ─┼──▶│ Importers│───▶│ ToolCall corpus│───▶│           │
 langfuse (later)┘   └──────────┘    └───────────────┘    │           │
                                                          │ Replayer  │──▶ Transitions ──▶ Reporters
 git ref A ──▶ PolicyLoader ──▶ policy dir A ──▶ Evaluator A ──▶│  (join   │      (terminal,
 git ref B ──▶ PolicyLoader ──▶ policy dir B ──▶ Evaluator B ──▶│  by id)  │       markdown,
                                                          └───────────┘       json, sarif)
```

Five components, one package, no daemon:

1. **Importers** turn a trace source into a stream of canonical `ToolCall`
   records. v0.1: permdiff JSONL, OpenTelemetry GenAI spans (OTLP JSON /
   JSONL), Custody `custody.trace.v1`. Later: Langfuse, LangSmith, Claude Code
   hook logs, OPA decision logs.
2. **PolicyLoader** materializes the policy directory at a git ref into a
   temporary directory using `git archive`. Never touches the working tree.
   `--head WORKTREE` uses uncommitted files for local iteration.
3. **Evaluators** implement one interface: `evaluate(calls, policy_dir) ->
   Decision[]`. v0.1: OPA (pinned `opa` binary, batch), Cedar (`cedarpy`,
   optional extra), Python callable. Later: TOLAP purpose binding, Custody.
4. **Replayer** runs every call through both evaluators with the recorded
   timestamp and context injected, joins decisions by call id, and classifies
   each pair into a transition.
5. **Reporters** group and sample transitions, apply redaction, and emit
   terminal, markdown (PR comment), JSON, and SARIF. Exit code follows
   `--fail-on`.

### 3.2 The canonical decision input: `ToolCall`

Every importer produces this. Every evaluator consumes it.

```json
{
  "id": "01J8Z9EXAMPLEULID0000000000",
  "timestamp": "2026-09-20T14:03:11.412Z",
  "principal": {"id": "alice@example.com", "type": "user", "attrs": {"department": "support"}},
  "agent":     {"id": "support-bot", "version": "1.4.0", "attrs": {}},
  "tool":      {"name": "stripe.refund", "server": "stripe-mcp", "type": "function"},
  "arguments": {"charge_id": "ch_3Nx", "amount": 750, "reason": "duplicate"},
  "resource":  {"type": "stripe.charge", "id": "ch_3Nx", "attrs": {"currency": "usd"}},
  "context":   {"session_id": "sess-9f2", "env": "prod", "cwd": "/srv/app"},
  "recorded":  {"effect": "allow", "policy_hash": "sha256:..."},
  "source":    {"format": "custody.trace.v1", "locator": "traces/2026-09-20.jsonl:1187"}
}
```

Rules:

- `id` is stable across runs. Importers use the source's id (ULID, span id,
  decision id) or derive `sha256(timestamp, principal, tool, arguments)`.
- `timestamp` is required. It is the replay clock.
- `principal`, `agent`, `tool.name` are required. Everything else optional;
  policies that need a missing field produce "can't evaluate", never "allow".
- `recorded` is what the runtime actually did, when the source knows. It is
  reported as a sanity signal ("base policy disagrees with recorded decision
  on 12 calls") but never used as a decision.
- `arguments` and `attrs` are opaque JSON. permdiff does not interpret them;
  it passes them to the engine and redacts them in reports.

Importer mappings (verified against current specs):

| Source | principal | agent | tool | arguments | timestamp |
|---|---|---|---|---|---|
| Custody `custody.trace.v1` ([spec](https://github.com/smhasan94/custody), PLAN.md §5) | `actor.user` | `actor.agent` | `action.name` | `action.input_redacted` (digest-only traces yield "can't evaluate" for argument-dependent rules) | `ts` |
| OTel GenAI `execute_tool` span ([semconv-genai](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md)) | `enduser.id` / `user.id` (span or resource attrs) | `gen_ai.agent.name` / `gen_ai.agent.id` | `gen_ai.tool.name` | `gen_ai.tool.call.arguments` (Opt-In, often absent; fallback to `tool_call` parts in the parent span's `gen_ai.output.messages`) | `startTimeUnixNano` |
| permdiff JSONL | as-is | as-is | as-is | as-is | as-is |

The OTel GenAI conventions moved to a separate repository in semconv v1.42 and
remain at "Development" stability with no tagged release. The importer accepts
the deprecated `gen_ai.system` and `gen_ai.choice` names as aliases and is
expected to need updates as the conventions stabilize.

### 3.3 The canonical output: `Decision` and transitions

```json
{"call_id": "01J8Z9…", "effect": "require_approval", "reasons": ["refund > 500"],
 "determining": ["policy/agent.rego:42"], "engine": "opa"}
```

`effect` is one of `allow`, `deny`, `require_approval`, `error`. `error` carries
a `kind`: `missing_context`, `nondeterministic`, `eval_error`, `unsupported`.

Effects are ordered `deny < require_approval < allow`. A transition is:

| base → head | class | default severity |
|---|---|---|
| any move up the order (`deny→allow`, `deny→require_approval`, `require_approval→allow`) | **widening** | fail |
| any move down (`allow→deny`, `allow→require_approval`, `require_approval→deny`) | tightening | warn |
| same effect, different determining policies | attribution change | info |
| `error` on either side | can't evaluate | warn (never counted as unchanged) |
| same effect, same determining policies | unchanged | none |

### 3.4 Evaluator adapters

**OPA.** permdiff runs a pinned `opa` binary (downloaded per platform, checksum
verified, cached under the user cache dir, overridable with `--opa-bin`).
Per ref it writes the corpus to `cases.json`, a generated shim module, and runs
one `opa eval` with `--strict-builtin-errors` and a restricted capabilities
file. Measured on OPA 1.21.0: 100K inputs in 0.62 s per ref, using a
comprehension of the form

```rego
results := [r |
  some c in data.permdiff.cases
  r := data.agent.authz.decision with input as c with time.now_ns as c.ts_ns
]
```

The decision path (`data.agent.authz.decision`) and the result mapping are
configurable. Default mapping: an object with `effect` and `reason`; fallback
to a boolean `allow`. Time is mocked per call with `with time.now_ns as`,
which OPA supports in any query context. Rego v1 syntax is assumed (OPA 1.x);
`--v0-compatible` is passed through for legacy policies.

**Cedar.** Via [`cedarpy`](https://pypi.org/project/cedarpy/) (4.12.1,
2026-09-24, wraps cedar-policy 4.12, `is_authorized_batch`). Installed with
`pip install permdiff[cedar]` because it is third-party and lags the Cedar
crate by about one minor version. Per ref permdiff loads `*.cedar`, the schema,
and an entities file from the policy directory. A `ToolCall` maps to a Cedar
request through configurable templates (default `principal =
User::"{principal.id}"`, `action = Action::"{tool.name}"`, `resource =
{resource.type}::"{resource.id}"`), with `arguments`, `context`, and `now`
(RFC 3339, for the stable `datetime` extension) merged into the Cedar
`context`. Cedar has only Allow/Deny: `require_approval` is a Deny whose
determining policies all carry the annotation `@require_approval` (configurable),
the same convention sbproxy uses.

**Python callable.** `--engine python:mypkg.policy:evaluate`, signature
`evaluate(call: ToolCall, policy_dir: Path) -> Decision`. The callable is
imported from the current environment; the policy directory at each ref is
passed in. This is the escape hatch for custom engines, YAML rule files, and
gateways with a Python SDK.

**Later.** TOLAP purpose binding (action validation against
`purposeProfile.allowedActions` / `prohibitedActions`, awslabs/tolap spec §15),
Custody's `/v1/check` semantics once Custody has code.

### 3.5 Git-aware policy loading

`permdiff diff --base <ref> --head <ref> --policy policy/`:

- Refs are validated with `git rev-parse --verify` and passed to git as
  arguments, never interpolated into a shell string.
- `git archive <ref> -- <policy-path>` is extracted to a per-run temporary
  directory. The working tree is never modified. `--head WORKTREE` copies the
  live directory instead, for local iteration before committing.
- Default `--base` is `origin/main` (overridable in config); default `--head`
  is `HEAD`.
- The report header records both resolved SHAs and the policy path so the
  comment is reproducible.

### 3.6 Grouping, sampling, redaction

Transitions are grouped by `(class, tool.name)` by default, with `--group-by`
accepting `tool`, `resource.type`, `agent.id`, `principal.id`, and `reason`.
Each group shows a count and up to `--samples N` (default 3) example calls.

Redaction (decision 5, "safe" default):

- Argument values become type+length placeholders: `{"charge_id": "<str:6>",
  "amount": "<int>"}`. Keys are kept.
- Tool, resource type, agent id, and reason strings are shown.
- Principal ids are shown in the terminal and replaced by a stable 8-character
  hash (`principal:3f9a1c2e`) in markdown, JSON, and SARIF.
- Grouping and sampling operate on hashed values, so counts are exact.
- `--show-args amount,currency` allowlists specific keys. `--redact none`
  exists for local use; `--format markdown` with `--pr-comment` refuses it.
- Sample selection is deterministic (sorted by call id) so repeated runs
  produce identical comments and the sticky-comment upsert is a no-op when
  nothing changed.

### 3.7 Nondeterminism and "can't evaluate" (decision 4)

- The replay clock is always the trace timestamp. Policies see the time the
  call happened, so time-window rules behave as they did.
- OPA runs with a capabilities file that omits `http.send`,
  `net.lookup_ip_addr`, `rand.intn`, `uuid.rfc4122`, and `opa.runtime`. A
  policy that uses them fails to compile for that ref; permdiff reports the
  offending builtin and marks every call `error/nondeterministic`. Users can
  pass `--nd-cache recorded.json` (OPA `nd_builtin_cache` shape) to replay
  recorded lookup results, which re-enables those builtins with `with`
  overrides.
- Cedar is deterministic by construction. Missing entities or context fields
  produce evaluation errors, which permdiff reports as `error/missing_context`
  with the field name.
- Python callables are trusted to be deterministic; permdiff documents this
  and runs the corpus twice in `--verify-deterministic` mode on request.
- Nothing in the `error` bucket is ever counted as `unchanged` or `allow`.

### 3.8 Outputs and exit codes

- `--format terminal` (default): the summary block at the top of this
  document, colored, with groups and samples.
- `--format markdown`: a PR comment with a `<!-- permdiff -->` marker,
  collapsible per-group sections, both SHAs in the header.
- `--format json`: full transition list plus per-call decisions, for scripts
  and for the GitHub Action to derive the other formats.
- `--format sarif`: SARIF 2.1.0. GitHub requires a physical location on every
  result, so each result anchors to the changed policy file (`artifactLocation.uri`
  = the determining policy file at head, `startLine` = the rule's line when
  known, else 1) and carries the tool and hashed principal in
  `logicalLocations` and `properties`. `partialFingerprints.primaryLocationLineHash`
  is a stable hash of (tool, principal hash, argument shape) so alerts dedupe
  across runs. SARIF is secondary; the PR comment is the primary surface.
- Exit codes: `0` nothing matched `--fail-on`; `2` matched (`widen` by default;
  also `any-change`, `cant-evaluate`, `none`); `1` permdiff itself failed
  (bad ref, engine unavailable, importer error). `--allow-widening` with a
  reason string records an override in the report for audited approvals.

### 3.9 Key design decisions and rejected alternatives

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Unit of replay | Authorization decisions | LLM behavior (cassette replay) | Policy impact is deterministic and cheap; model replay is a different product with different tools |
| Engine strategy | Pluggable evaluators; OPA + Cedar + Python in v0.1 | One engine, or a permdiff-native DSL | Teams already have policies; a new DSL is `authority-diff`'s mistake for this audience |
| OPA execution | Pinned `opa` binary, one process per ref, batch comprehension | Regorus bindings; per-call subprocess; OPA REST | Regorus is not on PyPI and stubs `http.send`; per-call subprocess is 12 ms each (20 min for 100K); REST needs a server |
| Cedar execution | `cedarpy` optional extra | Shell out to `cedar authorize` (one request per invocation); Rust core | `cedar authorize` has no batch mode; a Rust core kills `pip install` simplicity |
| Require-approval | Generic tri-state, per-engine mapping | Per-engine only; binary | Uniform reports; Cedar has no third decision so annotations are the only hook |
| Policy source | `git archive` at refs | Checkout into worktrees; ask user to export | No working-tree mutation; works in CI and locally |
| Time | Trace timestamp injected into engine | Wall clock | Time-scoped rules must replay as they happened |
| External lookups | Fail closed into "can't evaluate" | Live lookups behind a flag | Reproducible comments; no silent allow |
| Redaction | Safe by default, opt in to show | Full args by default | Traces contain PII; a PR comment is a publication |
| Distribution | Single `pip install`, no daemon, no service | Hosted service; Docker-first | Time-to-first-value; CI runners already have Python |
| Comparison basis | Trace corpus | Symbolic analysis | Answers "what changes on my traffic"; symbolic is a later complement |
| Canonical schema | permdiff `ToolCall` | Adopt `custody.trace.v1` wholesale | Standalone adoption; Custody is one importer |

### 3.10 Trust boundaries and threat model

```
┌─ untrusted ───────────────────────────────────────────────────────────┐
│ traces (PII, attacker-influenced content: prompt-injected arguments)  │
│ policy source at refs (executes inside the engine)                    │
│ PR head from forks (in CI)                                            │
└───────────────────────────────────────────────────────────────────────┘
        │ importers (parse only)      │ engines (sandboxed)      │ CI token scope
        ▼                             ▼                          ▼
┌─ permdiff process ────────────────────────────────────────────────────┐
│ ToolCall corpus (in memory / temp dir, never persisted by permdiff)   │
│ OPA subprocess: restricted capabilities, no network builtins          │
│ Cedar in-process: pure evaluation                                     │
│ Python callable: ARBITRARY CODE from the current environment          │
└───────────────────────────────────────────────────────────────────────┘
        │ reporters (redaction applied here, once, for every format)
        ▼
┌─ published ───────────────────────────────────────────────────────────┐
│ PR comment (visible to everyone with repo read), SARIF alerts, JSON   │
└───────────────────────────────────────────────────────────────────────┘
```

Assets: trace contents (PII, secrets in arguments), the integrity of the
transition report (a wrong "no widening" is the worst outcome), and the CI
token.

Threats and mitigations:

- **PII leakage into PR comments.** Redaction runs once in the reporter layer,
  for every format; the "safe" level is default; `--pr-comment` refuses
  `--redact none`; sample counts are capped; tests assert that raw argument
  values from fixture traces never appear in markdown/SARIF output.
- **Crafted traces.** Importers validate schema and size limits (line length,
  nesting depth, corpus size), reject non-UTF-8, and never evaluate trace
  content as code. Argument strings are opaque to permdiff. Prompt-injected
  text inside arguments reaches only the policy engine as data.
- **Policy code execution.** OPA runs as a subprocess with a capabilities
  allowlist and no network builtins. Cedar is pure. The Python callable is
  arbitrary code; permdiff documents that `--engine python:` runs code from
  the current environment and is appropriate in CI only where the head ref's
  code already runs (tests). It does not import from the base ref's tree.
- **Fork PRs.** GitHub grants read-only tokens to `pull_request` from forks.
  The Action degrades to the job summary and an artifact instead of failing,
  and documents the `workflow_run` pattern for commenting safely. It never
  recommends `pull_request_target` with fork checkout.
- **Command injection via refs and paths.** Refs are verified with `git
  rev-parse --verify`; git and opa are invoked with argument lists, never
  through a shell.
- **Supply chain.** The `opa` binary is pinned by version and SHA-256 per
  platform in the package; downloads go to the user cache; `--opa-bin` lets
  air-gapped users supply their own. `cedarpy` is pinned to a minor version.
  Runtime dependencies are kept to a handful (budget set in the PRD).
- **Wrong "no widening".** Golden tests compare permdiff's transitions against
  engine-native evaluation on fixture corpora; the `error` bucket is
  exhaustive (no silent drops); the report footer states the count of
  imported vs evaluated calls so a mismatch is visible.
- **Temp-file exposure.** Policy archives and `cases.json` go to a per-run
  `tempfile.mkdtemp` with 0700 permissions and are removed on exit, including
  on failure. `--debug` keeps them deliberately and prints the paths.
- **Nondeterministic policy input (learned in E2).** OPA runs with
  `--strict-builtin-errors` and a capabilities file that removes `http.send`,
  `net.lookup_ip_addr`, `rand.intn`, `uuid.rfc4122`, and `opa.runtime`; a
  policy using one is reported as nondeterministic rather than evaluated with
  live data. `--nd-cache` re-enables only the builtins it has recorded values
  for, replaces them with shim lookups, and never lets a cache miss fall back
  to the real builtin or to `default deny`; misses are surfaced per call.
- **Recorded lookup values are trace data (learned in E2).** An nd-cache file
  can carry HTTP response bodies. It is read from a user-supplied path, written
  into the per-batch 0700 temp directory only, and never into the user cache.
- **Action inputs (learned in E4).** Every user-controlled input reaches
  `permdiff` through argument files read with `mapfile`, never through shell
  word splitting; `extra-args` is split with `shlex`; `--redact safe` is
  appended last so `extra-args` cannot lower redaction in a posted report. The
  comment step runs only for same-repository pull requests.
- **Third-party plugins (learned in E1/E3).** Importer and evaluator entry
  points are loaded lazily; a plugin that fails to import is skipped with a
  warning for importers and is an error for engines; built-in names always win
  a collision. Installing a plugin is a code-execution decision the user makes
  with `pip`.
- **Policy-authored text (learned in the E7 security review).** `Decision.reasons`
  and `determining` come from the policy engine, so a policy can echo raw
  argument values into them. Under `safe`, every string or number the call
  carries (arguments, attributes, context, principal id, resource id) is
  scrubbed out of that text and the text is capped at 200 characters; the
  sentinel harness covers a policy that echoes trace values. Reason text is
  still policy-author controlled and can carry anything the policy invents.
- **Cedar (learned in E6).** Evaluation is in-process and pure; request
  templates are validated at engine construction; JSON nulls are dropped from
  context rather than passed through; policies are validated against the
  schema per ref and a validation failure marks every call, never allows.

Out of scope for the threat model: the correctness of the user's policy
engine, the runtime that produced the traces, and the trustworthiness of
repository collaborators who can edit the workflow file.

---

## 4. How developers will use it

### 4.1 Install

```
pip install permdiff            # OPA + Python callable engines
pip install "permdiff[cedar]"   # adds cedarpy
```

Python 3.11+. The `opa` binary is fetched on first use (or `permdiff setup
opa` to prefetch; `--opa-bin` to bring your own). No service, no database, no
API key.

### 4.2 Five-minute quickstart

```
# 1. Try it on the bundled example (30 s)
permdiff demo
# prints a diff between two bundled Rego policies over a 200-call fixture
# corpus, including one widening, and shows the exit code.

# 2. Point it at your own policy and traces (2 min)
cd my-agent-repo
permdiff diff --engine opa --policy policy/ \
  --decision data.agent.authz.decision \
  --base origin/main --head WORKTREE \
  --traces traces/*.jsonl

# 3. Save the config so the command is just `permdiff diff` (1 min)
permdiff init      # writes permdiff.toml from the flags above

# 4. Put it in CI (2 min)   see 4.3
```

If you have no traces yet, `permdiff record` is not part of v0.1; instead
`permdiff convert --from otel spans.jsonl` or `--from custody` turns existing
telemetry into permdiff JSONL, and the JSONL format is simple enough to emit
from any hook in ten lines (the README shows a Claude Code `PreToolUse` hook
that appends one).

### 4.3 Integration examples

**GitHub Actions, sticky PR comment:**

```yaml
name: permdiff
on: pull_request
permissions:
  contents: read
  pull-requests: write
jobs:
  permdiff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with: { fetch-depth: 0 }
      - uses: smhasan94/permdiff@v0
        with:
          traces: traces/*.jsonl
          base: origin/${{ github.base_ref }}
          fail-on: widen
```

The action is a composite: sets up Python, installs a pinned permdiff, runs
`permdiff diff --format json`, renders markdown, and upserts one comment
marked `<!-- permdiff -->` (update if present, create otherwise). On a fork PR
with a read-only token it writes the same markdown to the job summary and
uploads the JSON as an artifact. `sarif: true` additionally emits SARIF for
`github/codeql-action/upload-sarif@v4` (needs `security-events: write`).

**Custody traces:**

```
custody export --profile permdiff > traces/custody.jsonl
permdiff diff --traces traces/custody.jsonl --from custody
```

The importer reads `custody.trace.v1` events; digest-only exports
(`evidence.retention: digest_only`) produce "can't evaluate" for
argument-dependent rules, and the report says so.

**OpenTelemetry:**

```
# any OTLP/JSON file exporter output or a Jaeger JSON dump
permdiff diff --traces otel/*.jsonl --from otel
```

Only `execute_tool` and MCP `tools/call` spans are imported. Principal comes
from `enduser.id`/`user.id` or `--principal-from resource.attr.service.name`
when the traces carry no user.

**Cedar:**

```toml
# permdiff.toml
[policy]
engine = "cedar"
path = "policy/"          # *.cedar, schema.cedarschema, entities.json

[cedar]
principal = 'User::"{principal.id}"'
action    = 'Action::"{tool.name}"'
resource  = '{resource.type}::"{resource.id}"'
approval_annotation = "require_approval"
```

**Custom engine (Python):**

```python
# authz/permdiff_adapter.py
from pathlib import Path
from permdiff import ToolCall, Decision
from authz.engine import load_rules, check


def evaluate(call: ToolCall, policy_dir: Path) -> Decision:
    rules = load_rules(policy_dir / "rules.yaml")
    verdict = check(rules, call.principal.id, call.tool.name, call.arguments, at=call.timestamp)
    return Decision.from_effect(verdict.effect, reasons=[verdict.reason])
```

```
permdiff diff --engine python:authz.permdiff_adapter:evaluate --policy authz/
```

**Local pre-commit use:**

```
permdiff diff --head WORKTREE --fail-on any-change --format terminal
```

### 4.4 Configuration

`permdiff.toml` at the repo root (flags override it):

```toml
[policy]
engine = "opa"                     # opa | cedar | python:<module>:<callable>
path = "policy/"
base = "origin/main"

[opa]
decision = "data.agent.authz.decision"
result = "object"                  # object (effect/reason) | bool
capabilities = "default"           # default (no network) | path to file
nd_cache = ""                      # recorded nd_builtin_cache for replay
version = "1.21.0"

[traces]
paths = ["traces/*.jsonl"]
format = "auto"                    # auto | permdiff | otel | custody
since = "7d"                       # window on trace timestamps

[report]
redact = "safe"                    # safe | none (local only)
show_args = []
samples = 3
group_by = ["tool"]
fail_on = "widen"                  # widen | any-change | cant-evaluate | none
```

Environment variables mirror the keys (`PERMDIFF_REPORT_REDACT`) for CI.

---

## 5. Non-goals

- **Not a policy decision point.** permdiff never enforces anything at runtime.
- **Not a trace collector or store.** It reads files. Recording is the job of
  the runtime, Custody, or your telemetry stack.
- **Not LLM replay or evaluation.** Nothing about model outputs, prompts, or
  trajectories.
- **Not symbolic analysis.** It reports what changes on recorded traffic, not
  what could change on all possible traffic. Cedar symcc and IAM Access
  Analyzer do that; a later mode may call them.
- **Not a policy language, authoring UI, or linter.** Bring your engine.
- **Not a judgment on legitimacy.** A recorded call that was allowed is not
  assumed to have been correct. permdiff shows transitions; humans decide.
- **No hosted service, dashboard, or account** in v0.1.
- **No per-engine formal semantics.** Adapters use the engine's own evaluator;
  permdiff does not reimplement Rego or Cedar.

---

## 6. Success signals

**Time-to-first-value (the top priority)**

- A developer with an OPA or Cedar policy in git and any tool-call log can
  produce a real diff within five minutes of opening the README. Measured by
  timing three people who have never seen the project.
- `permdiff demo` works offline immediately after `pip install`.

**Quality**

- Transitions match engine-native evaluation on golden corpora for OPA and
  Cedar, 100%, in CI.
- 100K calls diffed in under 60 s on a laptop (target to confirm in Phase 2;
  the OPA engine alone measures 0.62 s per ref, so importer and reporter
  budgets dominate).
- Zero leaks: a test corpus seeded with sentinel PII values never produces a
  markdown, JSON, or SARIF output containing them, enforced by a test on every
  reporter.
- The `error` bucket is never empty when it should not be: fixtures with
  missing context and `http.send` policies produce the expected counts.
- Identical inputs produce byte-identical markdown (sticky comment stays
  quiet).

**Adoption**

- Public repositories running the GitHub Action (searchable by `uses:
  smhasan94/permdiff`).
- Issues and PRs from people who are not the author, especially new importers
  and evaluator adapters.
- At least one engine or agent-runtime project linking to permdiff from its
  docs as the way to test policy changes.
- Custody consumes permdiff as its policy-PR check rather than building its
  own.
