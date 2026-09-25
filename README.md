# permdiff

`terraform plan` for AI agent permission changes.

permdiff replays a corpus of recorded agent tool calls against an authorization
policy at two git refs and reports which calls change decision: what becomes
denied, what becomes allowed, what now needs human approval, and what could not
be evaluated. It never calls a model. It replays decisions.

```
$ permdiff diff --base origin/main --head HEAD --traces traces/*.jsonl

permdiff: origin/main → HEAD   (4,812 calls, 2026-09-18 → 2026-09-25)
  newly DENIED             37   aws.ec2.terminate_instance
  newly ALLOWED             2   github.delete_branch          ⚠ widening
  now REQUIRE_APPROVAL    118   stripe.refund
  can't evaluate            9   missing context: principal.department
  unchanged             4,646
```

## Status

Pre-release. Under construction; see `docs/03-epics.md` for progress.

## Install

```
pip install permdiff
```

Python 3.11 or newer.

## Quickstart

**1. Try it on the bundled example (30 seconds).**

```
permdiff demo
```

This diffs two bundled policy versions over a synthetic 200-call corpus and
prints one widening group (`github.delete_branch` newly allowed outside
prod), two tightening groups, and a can't-evaluate group where the new policy
needs a `department` attribute the traces lack. It exits `2` because a
widening was found. Nothing is downloaded and no network is used.

The demo uses the pinned OPA binary when it is installed and otherwise the
bundled Python engine. To see the Rego version:

```
permdiff setup opa          # downloads opa 1.21.0 into your user cache, checksum verified
permdiff demo --engine opa
```

**2. Point it at your own policy and traces.**

```
permdiff diff --base origin/main --head HEAD --policy policy/ \
              --engine opa --decision data.agent.authz.decision \
              --traces traces/*.jsonl
```

With `--engine opa` every trace becomes `input`, `time.now_ns()` returns the
trace's timestamp, and the decision rule may return an object
(`{"effect": "allow|deny|require_approval", "reason": "...", "rule": "..."}`),
a boolean, or an effect string. `{"effect": "error", "kind": "missing_context",
"reason": "principal.attrs.department"}` reports a call the policy cannot
decide. Rules that stay undefined count as `deny` (`--undefined error` to
flag them instead). OPA runs with `http.send`, `net.lookup_ip_addr`,
`rand.intn`, `uuid.rfc4122`, and `opa.runtime` removed from its capabilities;
a policy that uses one is reported as nondeterministic for every call unless
you replay recorded values with `--nd-cache decision-log.json` (OPA's
`nd_builtin_cache` shape). `permdiff check` validates traces and compiles both
refs without diffing, which is what CI runs first.

**3. Put it in CI.**

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
```

The action runs `permdiff check`, then `diff`, and upserts one PR comment marked
`<!-- permdiff -->` that updates in place on every push. The check fails on
widening (`fail-on: widen`). Fork PRs, whose token is read-only, get the same
report in the job summary and as an artifact. `sarif: "true"` adds a SARIF file
for `github/codeql-action/upload-sarif@v4`. Inputs and outputs are in
[docs/action.md](docs/action.md). Save the flags once with `permdiff init` and
commit `permdiff.toml`; flags override environment variables
(`PERMDIFF_REPORT_FAIL_ON=none`) which override the file.

For a Python policy adapter instead:

```
permdiff diff --base origin/main --head HEAD --policy policy/ \
              --engine python:authz.permdiff_adapter:evaluate \
              --traces traces/*.jsonl
```

`diff` replays every trace against the policy at both refs and prints the
summary block above. Exit code `2` means the run matched `--fail-on`
(`widen` by default), `1` means permdiff itself failed, `0` means nothing
matched. `--head WORKTREE` uses the uncommitted policy in your working tree.

Traces are JSONL, one `ToolCall` per line; `permdiff schema toolcall` prints
the JSON Schema. Reports redact argument values by default; `--show-args`
reveals named keys and `--redact none` shows everything for local use.

`--format markdown|json|sarif` and `permdiff render --from-json` produce the
other outputs; `permdiff schema report` prints the JSON report's schema. The
Cedar engine and the Custody and OpenTelemetry importers arrive in the next
epics. The design is in `docs/01-overview.md`.

## Engines

`--engine cedar` (`pip install "permdiff[cedar]"`) loads `*.cedar` files, one
`*.cedarschema`, and `entities.json` from the policy path, validates the policies
against the schema, and evaluates every trace as a Cedar request built from the
`[cedar]` templates (`principal`, `action`, `resource`; defaults
`User::"{principal.id}"`, `Action::"{tool.name}"`, `Resource::"{resource.id}"`).
The request context is the call's arguments plus its trace context, plus
`context.call.{principal,agent,tool,resource}` and `context.now` (the trace
timestamp as a Cedar `datetime`). A deny whose forbids all carry
`@require_approval("reason")` is reported as require-approval; a missing
attribute or entity is can't-evaluate naming it. `permdiff demo --engine cedar`
runs the bundled Cedar variant.

Measured on an Apple M-series laptop: 100,000 calls per ref take about 12 s
through cedarpy (the OPA engine takes about 5 s for the same corpus).

`--engine opa` runs a pinned OPA binary (1.21.0, SHA-256 verified on
download; override with `--opa-bin` or `PERMDIFF_OPA_BIN`).

`--engine python:module.path:callable` calls your own Python function with
signature `(call: ToolCall, policy_dir: Path) -> Decision | str` for every
trace. **This imports and runs arbitrary code from the current environment**
with your permissions; point it only at code you would run directly.

## License

Apache-2.0.
