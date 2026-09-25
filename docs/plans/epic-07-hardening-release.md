# Plan: E7 — Performance, hardening, release preparation

**Source**: [03-epics.md](../03-epics.md) E7; NFR-P, NFR-S, NFR-Q5, NFR-L2
**Complexity**: Small (3 stories)
**Status**: reviewed 2026-09-25 (code-review low: findings fixed in 04cb831; 0.1.0 released)

## Summary

Prove and enforce the 60 s / 100K target, run the security checklist, and
prepare (not publish) the 0.1.0 release.

## Files to create or change

| File | Action | Why |
|---|---|---|
| `bench/generate.py` | CREATE | synthetic 100K corpus, seedable, no PII |
| `bench/run.py` | CREATE | end-to-end timing per phase (import, eval base, eval head, classify, report) for OPA and Python engines; JSON output |
| `bench/baseline.json` | CREATE | checked-in numbers from the reference laptop |
| `.github/workflows/bench.yml` | CREATE | runs `bench/run.py` on Linux; fails if any phase > 1.5× baseline |
| `pyproject.toml` | UPDATE | ruff `S602/S604` (shell=True) as errors; `pip-audit` dev dep |
| `.github/workflows/ci.yml` | UPDATE | `pip-audit`, wheel/sdist build, `twine check` |
| `CHANGELOG.md` | CREATE | 0.1.0 |
| `docs/release.md` | CREATE | owner's publishing checklist: PyPI, tag `v0.1.0`, move `v0`, GitHub release notes |
| `README.md` | UPDATE | benchmark numbers, final quickstart |

## Tasks

1. **E7-S1 benchmark** — tests: generator determinism; runner produces the JSON shape; CI gate logic unit-tested with a fake baseline.
2. **E7-S2 hardening** — actions: ruff rules, temp-dir permission tests on POSIX, `pip-audit`, re-read threat model and update, run the security-review checklist from the standing rules, fix findings.
3. **E7-S3 release prep** — actions: version `0.1.0`, changelog, build, `twine check`, `docs/release.md`; then halt and hand to the owner (standing rule 5).

## Validation

```bash
uv run python bench/run.py --engine opa --n 100000
uv run pip-audit
uv build && uv run twine check dist/*
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| CI runner slower than the laptop baseline | High | gate on ratio to a CI-specific baseline captured on first green run, not the laptop numbers |
| Import phase dominates (pydantic) | Medium | profile; `model_validate_json`; if still > 20 s, add optional `orjson` extra |

## Acceptance

- [x] All three stories done and marked
- [x] README shows measured numbers under target (6.5 s Python, 11.8 s OPA, under 1 GiB)
- [x] Owner handed a ready-to-publish 0.1.0 (docs/release.md); publishing itself is the owner's
