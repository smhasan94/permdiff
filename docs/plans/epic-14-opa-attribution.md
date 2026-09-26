# Plan: E14 — OPA rule attribution to file:line

**Source**: [03-epics.md](../03-epics.md) E14; FR-L7
**Complexity**: Small (2 stories, about half a day)
**Status**: planned 2026-09-26

## Summary

Build a static rule index per ref from `opa parse --json-include locations`, attach
`file:row` locations to OPA decisions in a new additive `Decision.locations` field, and
have SARIF and the sample renderers use it. No per-call explain traces.

## Verified 2026-09-26

- `opa parse -f json --json-include locations` on the pinned 1.21.0 (see the E14 entry).
- `report/sarif._location` parses `file:line` from `determining` today (regex
  `_FILE_LINE`); the demo Python engine's `determining` is `rules.py:<tool>=<effect>`,
  which does not match, so SARIF falls back to the first policy file.
- `models/transition.py:35` compares `base.determining != head.determining` for
  attribution changes; `locations` stays out of that comparison.
- `_proc.run(argv)` returns `ProcResult` with `ok`, `stdout`, `stderr`.
- Goldens: `tests/unit/report/test_json.py` and `tests/integration/test_demo_opa.py`
  accept `UPDATE_GOLDEN=1`; the JSON golden includes decisions, so it gains
  `"locations": []` entries.

## Patterns to mirror

| Category | Source | Pattern |
|---|---|---|
| Subprocess | `evaluators/opa/evaluator.py:prepare` | `_proc.run`, warnings on failure, never raise for a single ref |
| Frozen models | `models/decision.py` | additive tuple field with a default |
| Report rendering | `report/markdown._sample_row`, `report/terminal._sample_line` | reasons cell |
| Tests | `tests/integration/test_cli_opa.py` (`rego_repo`, `opa_bin`) | OPA tests skip without the binary |

## Files to create or change

| File | Action | Why |
|---|---|---|
| `src/permdiff/models/decision.py` | UPDATE | `locations` field; `from_effect`/`error` pass-through |
| `src/permdiff/evaluators/opa/ruleindex.py` | CREATE | `RuleIndex`, `build`, `labels_of_head`, `attach` |
| `src/permdiff/evaluators/opa/evaluator.py` | UPDATE | index in `OpaPrepared`; attach in `_decide` |
| `src/permdiff/report/sarif.py`, `markdown.py`, `terminal.py` | UPDATE | use `locations` |
| `tests/unit/evaluators/opa/test_ruleindex.py` | CREATE | parse fixture rego with the binary (skips without it); label, name, and package matching; bad file |
| `tests/unit/report/test_sarif.py`, `test_markdown.py`, `test_terminal.py` | UPDATE | locations rendering |
| `tests/integration/test_cli_opa.py` | UPDATE | SARIF uri/line and JSON locations end to end |
| `tests/golden/json_report.json` | UPDATE | regenerated (`locations: []`) |
| `docs/importers.md`? no; `docs/01-overview.md`/`README.md` one line; `CHANGELOG.md`; `docs/03-epics.md` | UPDATE | docs and statuses |

## Interfaces

```python
# evaluators/opa/ruleindex.py
class RuleIndex(Frozen):
    by_label: Mapping[str, str]      # "read" -> "agent.rego:7"
    by_name: Mapping[str, str]       # "decision" -> first definition; "agent.authz.decision" too
    def lookup(self, label: str) -> str | None
def build(binary: Path, policy_dir: Path, *, extra_flags: Sequence[str | Path] = ()) -> RuleIndex
def attach(decision: Decision, index: RuleIndex) -> Decision   # model_copy with locations
```

## Tasks

1. **S1** tests first: `labels_of_head` on AST snippets (object with `rule`, with `rules`
   array, non-object head); `build` on `tests/fixtures/opa/basic` (label `read` → `agent.rego:7`,
   `refund-large` → its row, name `decision` → first row, unknown → None); evaluator
   attaches locations (integration via `_run` with `--format json --include-decisions`).
2. **S2** tests first: SARIF picks `locations` over fallback; markdown/terminal append
   `@ file:row`; regenerate the JSON golden; docs; CHANGELOG; statuses.

## Validation

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q
UPDATE_GOLDEN=1 uv run pytest -q tests/unit/report/test_json.py && git diff --stat tests/golden
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Labels reused across rules or files | Medium | first definition wins, documented; name and package fallbacks |
| Policies return rule names that are computed, not literals | Medium | no location, nothing else changes |
| Extra `opa parse` per file slows large policies | Low | one process per file per ref, only in `prepare` |

## Acceptance

- [ ] Both stories done and marked
- [ ] Validation passes; CI green
- [ ] SARIF for an OPA diff points at the rego line
