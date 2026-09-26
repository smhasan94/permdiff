# Plan: E15 — HTML report

**Source**: [03-epics.md](../03-epics.md) E15; FR-L10
**Complexity**: Small (2 stories, about half a day)
**Status**: done 2026-09-26 (S1, S2); review pending

## Summary

A fourth text renderer beside markdown, terminal, and SARIF: one HTML document built from
the same `ReportView`, inline CSS, no JavaScript. Wired into `--format` everywhere the
other formats are.

## Verified 2026-09-26

- `report/markdown.py` is the model: `_header`, `_summary`, `_group`, `_sample_row`,
  `_footer` over `ReportView`; `_CLASS_ICON` labels; `gate_reason` for the footer.
- `cli/_render.py` `FORMATS` tuple and `PRINCIPAL_SHOWN_IN` gate principal hashing;
  `emit_and_exit` dispatches on `opts.fmt`; `cli/render.py` dispatches again for
  `render --from-json`; `config/model.py` `ReportConfig.format` is a `Literal`.
- Tests: `tests/unit/report/test_markdown.py` uses `sample_report()`, `FIXED_SALT`,
  `build_view`, the redaction harness, and a golden under `tests/golden/` with
  `UPDATE_GOLDEN=1`.

## Files to create or change

| File | Action | Why |
|---|---|---|
| `src/permdiff/report/html.py` | CREATE | `render_html` |
| `src/permdiff/report/__init__.py` | UPDATE | export |
| `src/permdiff/cli/_render.py`, `cli/render.py`, `config/model.py`, `cli/settings.py` (choice help) | UPDATE | `html` format |
| `action.yml`, `docs/action.md` | UPDATE | format input if present |
| `tests/unit/report/test_html.py`, `tests/golden/html_report.html` | CREATE | golden, escaping, no script/external refs, sentinels |
| `tests/integration/test_cli_diff.py`, `test_cli_render.py` (or existing render tests) | UPDATE | `--format html` end to end |
| `scripts/quickstart_check.sh`, `README.md`, `CHANGELOG.md`, `docs/03-epics.md` | UPDATE | docs and statuses |

## Tasks

1. **S1** tests first (golden, escaping of `<`, `&`, quotes in ids and reasons, no
   `<script>`/`http` refs, sentinel harness, byte-identical), then the renderer.
2. **S2** tests first for `diff --format html --output`, `render --format html`,
   config `report.format = "html"`; then plumbing, docs, quickstart, CHANGELOG.

## Validation

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q
uv run permdiff demo --format html --output /tmp/permdiff.html --fail-on none && grep -c "<script" /tmp/permdiff.html
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Unescaped trace values | Low | `html.escape` on every value; sentinel and escaping tests |
| CSS drift makes the golden churn | Low | CSS lives in one constant; golden regenerated deliberately |

## Acceptance

- [ ] Both stories done and marked
- [ ] Validation passes; CI green
- [ ] The demo renders to one HTML file with no script or external reference
