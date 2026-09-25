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

**2. Point it at your own policy and traces.**

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

OPA and Cedar engines, markdown/JSON/SARIF output, and the GitHub Action
arrive in the next epics. The design is in `docs/01-overview.md`.

## Engines

`--engine python:module.path:callable` calls your own Python function with
signature `(call: ToolCall, policy_dir: Path) -> Decision | str` for every
trace. **This imports and runs arbitrary code from the current environment**
with your permissions; point it only at code you would run directly. OPA and
Cedar adapters arrive in later stories.

## License

Apache-2.0.
