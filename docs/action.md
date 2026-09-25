# GitHub Action reference

`smhasan94/permdiff@v0` is a composite action. One step per workflow gives you a
sticky PR comment and a failing check on widening.

```yaml
name: permdiff
on: pull_request
permissions:
  contents: read
  pull-requests: write        # for the sticky comment; read-only still works (see below)
jobs:
  permdiff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with: { fetch-depth: 0 }   # both refs must be present
      - uses: smhasan94/permdiff@v0
        with:
          traces: traces/*.jsonl
```

Everything not given as an input falls back to `permdiff.toml` in the repository, then to
permdiff's defaults.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `traces` | `permdiff.toml` `[traces] paths` | Trace file or glob |
| `base` | `origin/<PR base branch>`, else `origin/main` | Base git ref; fetched with depth 1 if missing |
| `head` | `HEAD` | Head git ref or `WORKTREE` |
| `policy` | `[policy] path` | Policy path in the repository |
| `engine` | `[policy] engine` | `opa` or `python:module:callable` |
| `decision` | `[opa] decision` | OPA decision path |
| `fail-on` | `widen` | `widen`, `any-change`, `cant-evaluate`, `none` |
| `comment` | `true` | Post or update the sticky PR comment |
| `sarif` | `false` | Also write a SARIF 2.1.0 file |
| `config` | nearest `permdiff.toml` | Config file path |
| `version` | empty | permdiff version from PyPI; empty installs the action's own source |
| `python-version` | `3.12` | Python for `actions/setup-python` |
| `extra-args` | empty | Appended verbatim to `permdiff diff` (for example `--allow-widening "ticket-42"`) |

## Outputs

| Output | Meaning |
|---|---|
| `exit-code` | `0` nothing matched `fail-on`, `2` matched, `1` permdiff failed |
| `report-json` | Path to the JSON report (also uploaded as the `permdiff-report` artifact) |
| `report-markdown` | Path to the markdown report |
| `sarif-file` | Path to the SARIF file when `sarif: true` |

## What the action does

1. `actions/setup-python`, then `pip install permdiff==<version>` (or the action source).
2. `permdiff check`: traces parse and the policy compiles at both refs, else exit 1.
3. `permdiff diff --format json --include-decisions`, exit code captured.
4. `permdiff render` turns the JSON into markdown (always appended to the job summary)
   and SARIF when requested.
5. On a same-repository pull request with `pull-requests: write`, one comment marked
   `<!-- permdiff -->` is created or updated in place. Identical content is not re-posted.
6. The report directory is uploaded as an artifact and the step exits with permdiff's code.

Principal ids are hashed with a salt derived from the repository id, so hashes are stable
across runs of the same repository and the comment update is a no-op when nothing changed.
Argument values are always redacted in the comment (`--redact none` is refused for PR
comments).

## Fork pull requests and read-only tokens

Fork PRs get a read-only `GITHUB_TOKEN`, so the comment step is skipped. The same markdown
is written to the job summary and the JSON report is uploaded as an artifact. If the token
turns out to be read-only for another reason, the comment step logs a warning and the job
still passes or fails on permdiff's exit code alone.

To comment on fork PRs anyway, run the action on `pull_request_target` with a checkout of
the PR head, or post from a separate `workflow_run` job that downloads the artifact.

## SARIF upload

```yaml
      - uses: smhasan94/permdiff@v0
        id: permdiff
        with:
          traces: traces/*.jsonl
          sarif: "true"
      - uses: github/codeql-action/upload-sarif@v4
        if: always() && steps.permdiff.outputs.sarif-file != ''
        with:
          sarif_file: ${{ steps.permdiff.outputs.sarif-file }}
```

`upload-sarif` needs `security-events: write`. One SARIF result is emitted per group
(class plus grouping key), anchored to the determining policy file and line when the
engine reports one, otherwise the first policy file at line 1. Widening results are
`error` level with security-severity 8.0.

## Approving a widening

```yaml
        with:
          extra-args: --allow-widening "SEC-142: release bot may delete merged branches"
```

The reason and the actor (`GITHUB_ACTOR`) appear in every report format and the check
passes with exit 0 while the widening remains visible.
