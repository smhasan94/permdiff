# Plan: E4 — GitHub Action

**Source**: [03-epics.md](../03-epics.md) E4; FR-26
**Complexity**: Small (2 stories)
**Status**: planned 2026-09-25

## Summary

A composite action at the repo root that installs a pinned permdiff, runs
`check` then `diff --format json`, renders markdown, and upserts one marked PR
comment. Degrades to job summary and artifact on read-only tokens. Optional
SARIF file output. The repo dogfoods it.

## Patterns to mirror

Sticky-comment marker pattern (`<!-- permdiff -->`, list → find → update/create) via
`actions/github-script`; composite action structure per GitHub docs; E3 reporters.

## Files to create or change

| File | Action | Why |
|---|---|---|
| `action.yml` | CREATE | composite action; inputs `traces`, `base`, `head`, `policy`, `engine`, `decision`, `fail-on`, `sarif`, `version`, `config`, `python-version`, `comment` (bool) |
| `action/render.py` | CREATE | thin wrapper: JSON → markdown/SARIF via `permdiff` API (keeps logic in the package) |
| `action/comment.js` | CREATE | upsert script used by `github-script` |
| `.github/workflows/dogfood.yml` | CREATE | runs the action on the demo fixture for every PR to this repo |
| `src/permdiff/cli/diff.py` | UPDATE | `--salt` default from `GITHUB_REPOSITORY_ID` when present; `--allow-widening` actor from `GITHUB_ACTOR` |
| `README.md` | UPDATE | integration section, fork PR note, SARIF upload snippet |
| `docs/action.md` | CREATE | inputs/outputs reference |

## Interfaces

```yaml
# action.yml (shape)
inputs:
  traces: {required: true}
  base: {default: "origin/${{ github.base_ref }}"}   # resolved in a step, not in defaults
  head: {default: "HEAD"}
  policy: {default: ""}      # falls back to permdiff.toml
  engine: {default: ""}
  fail-on: {default: "widen"}
  sarif: {default: "false"}
  comment: {default: "true"}
  version: {default: "0.1.0"}
  python-version: {default: "3.12"}
outputs:
  exit-code, report-json, report-markdown, sarif-file
runs:
  using: composite
  steps:
    - setup-python
    - pip install "permdiff==<version>" (plus [cedar] when engine == cedar)
    - permdiff check ...
    - permdiff diff --format json --output report.json ... ; capture exit code (continue-on-error)
    - render markdown + sarif from JSON
    - github-script upsert (if comment && token can write) else write $GITHUB_STEP_SUMMARY + upload-artifact
    - exit with captured code
```

Write-permission detection: attempt `listComments`; on 403 for `createComment`, fall
back. Simpler and reliable: check `github.event.pull_request.head.repo.full_name !=
github.repository` → fork → summary path.

## Tasks

1. **E4-S1 action + upsert** — tests: `action/comment.js` unit-tested with a mocked octokit (node test runner, no npm deps); `render.py` tested via pytest; dogfood workflow green on a PR to this repo (manual verification recorded in the story). Action: files above.
2. **E4-S2 fork fallback, SARIF, docs** — tests: fallback path exercised by a workflow matrix that sets `permissions: {pull-requests: read}`; SARIF file produced and validated with the E3 schema test; README and `docs/action.md`.

## Test strategy

Unit tests for the two scripts; the composite itself verified by the dogfood workflow
(cannot run locally). Keep all logic in the package so the action is glue.

## Validation

```bash
uv run pytest tests/unit/action
node --test action/
# then open a PR to this repo and confirm one comment, updated on the second push
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `pip install permdiff==0.1.0` fails before publishing | High during dev | `version: ""` installs from `${{ github.action_path }}` (the checked-out action source); dogfood uses that |
| Fork PRs get no comment | Certain | documented; summary + artifact; `workflow_run` recipe in docs |
| Comment upsert races on rapid pushes | Low | idempotent (find-then-update); last write wins |
| Base ref not fetched (shallow clone) | High | action step runs `git fetch --no-tags --depth=1 origin <base>` before diff; docs recommend `fetch-depth: 0` |

## Acceptance

- [ ] Both stories done and marked
- [ ] Dogfood PR shows one comment that updates in place and fails the check on the demo widening
