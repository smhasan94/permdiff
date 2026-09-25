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
```

More arrives with each story. The design is in `docs/01-overview.md`.

## License

Apache-2.0.
