# Plan: E4 — GitHub Action

**Source**: [03-epics.md](../03-epics.md) E4; FR-26
**Complexity**: Small (2 stories)
**Status**: reviewed 2026-09-25 (code-review low: 3 findings fixed; dogfood workflow green on main; PR comment verification pending owner)

## Summary

A composite action at the repo root that installs a pinned permdiff, runs
`check` then `diff --format json`, renders markdown, and upserts one marked PR
comment. Degrades to job summary and artifact on read-only tokens. Optional
SARIF file output. The repo dogfoods it.

## Updated 2026-09-25 (re-read before starting)

- Action versions verified via the GitHub releases API on 2026-09-25: `actions/checkout@v7`,
  `actions/setup-python@v7`, `actions/github-script@v9`, `actions/upload-artifact@v7`,
  `actions/cache@v6`, `github/codeql-action/upload-sarif@v4`.
- `action/render.py` is dropped. The E3 JSON envelope already carries everything the
  markdown and SARIF renderers need, so the package gains `permdiff render --from-json
  report.json --format markdown|sarif`, and the action calls that. No logic lives in the
  action.
- `pip install permdiff==<version>` cannot work before the package is published (standing
  rule 5 forbids publishing). `version: ""` (the default until release) installs from
  `${{ github.action_path }}`, and the dogfood workflow uses that.
- Standing rule 2 (no branches, no PRs) conflicts with the acceptance item "dogfood PR shows
  one comment that updates in place". The comment upsert is unit-tested with a mocked
  octokit, and the dogfood workflow runs on pushes to `main` where it exercises the
  job-summary path. PR-based verification is left to the owner; halted for a decision at the
  end of the epic (recorded in decisions.md when answered).
- Fork detection: `github.event.pull_request.head.repo.full_name != github.repository`
  selects the summary-plus-artifact path; a comment attempt that fails with 403 also falls
  back to the summary so a missing `pull-requests: write` permission never fails the job.
- Salt: the action passes `--salt` derived from `GITHUB_REPOSITORY_ID` so hashes are stable
  across runs within a repository and the sticky comment update is a no-op when nothing
  changed.

## Patterns to mirror

Sticky-comment marker pattern (`<!-- permdiff -->`, list → find → update/create) via
`actions/github-script`; composite action structure per GitHub docs; E3 reporters.

## Files to create or change

| File | Action | Why |
|---|---|---|
| `action.yml` | CREATE | composite action; inputs `traces`, `base`, `head`, `policy`, `engine`, `decision`, `fail-on`, `sarif`, `version`, `config`, `python-version`, `comment` (bool) |
| `src/permdiff/cli/render.py` | CREATE | `permdiff render --from-json FILE --format markdown\|sarif\|terminal` |
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
2. **E4-S2 fork fallback, SARIF, docs** — the fork path is a condition in `action.yml` (head repo differs) plus the 403 fallback in `comment.js`, both unit-tested; a permissions matrix workflow was dropped because a same-repo push cannot simulate a fork token. SARIF via `permdiff render`; README and `docs/action.md`.

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

- [x] Both stories done and marked
- [ ] Dogfood PR shows one comment that updates in place and fails the check on the demo widening (owner verification; see decisions.md 2026-09-25; the push-triggered dogfood run and the mocked-octokit unit tests cover what the agent can run)
