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

```
permdiff --version
permdiff diff --base origin/main --head HEAD --policy policy/ \
              --engine python:authz.permdiff_adapter:evaluate \
              --traces traces/*.jsonl
```

`diff` replays every trace against the policy at both refs and prints the
summary block above. Exit code `2` means the run matched `--fail-on`
(`widen` by default), `1` means permdiff itself failed, `0` means nothing
matched. `--head WORKTREE` uses the uncommitted policy in your working tree.

More arrives with each story. The design is in `docs/01-overview.md`.

## Engines

`--engine python:module.path:callable` calls your own Python function with
signature `(call: ToolCall, policy_dir: Path) -> Decision | str` for every
trace. **This imports and runs arbitrary code from the current environment**
with your permissions; point it only at code you would run directly. OPA and
Cedar adapters arrive in later stories.

## License

Apache-2.0.
