# Plan: E3 — Reporting, grouping, config

**Source**: [03-epics.md](../03-epics.md) E3; FR-6, FR-16, FR-17, FR-19, FR-20, FR-21, FR-23
**Complexity**: Medium (6 stories)
**Status**: reviewed 2026-09-25 (code-review low: 3 findings fixed)

## Summary

Turn a `Report` into PR-ready markdown, versioned JSON, and SARIF, with
grouping and deterministic sampling shared by all reporters, `permdiff.toml`
configuration with precedence, and trace filters.

## Updated 2026-09-25 (re-read before starting)

- E1-S8 already created `report/grouping.py` (`Group` with `cls`, `key`, `count`,
  `samples`, sorted widening first, deterministic samples by call id) and
  `report/summary.py` (summary rows shared by reporters); the terminal reporter consumes
  both. S1 generalizes `Group.key` into `GroupKey(cls, parts)` for combinable
  `--group-by` fields, adds `max_groups` truncation and `show_attribution`, and
  introduces `ReportView` as the single redacted, grouped, sampled structure. The
  terminal reporter migrates to `ReportView` in S1 so all four formats share one input.
- `[opa] result = object|bool` is dropped: the mapping already accepts objects,
  booleans, and effect strings per call. `[opa] version` selects the pinned download
  version (`permdiff setup opa --version` semantics); `[opa] capabilities` accepts
  `default` or a file path; `[opa] nd_cache` a file path.
- The SARIF 2.1.0 schema is vendored at `tests/vendor/sarif-schema-2.1.0.json`
  (schemastore copy of the OASIS schema, draft-07) and validated with `jsonschema`.
- Markdown headers print the salt (AC-17.1) and both SHAs; `--pr-comment` refuses
  `--redact none` with exit 1 (AC-17.3). GitHub's comment body limit is 65,536
  characters; the markdown reporter targets < 60 KB on the demo and truncates groups
  beyond `--max-groups` (default 50) with a note.
- `--since 7d` is relative to the newest trace timestamp, not the wall clock, so CI
  runs are reproducible; the header shows the effective window.
- `--engine` stays required on the command line until S5 makes `[policy] engine`
  (default `opa`) the fallback; `[traces] paths` becomes the default for `--traces`.
- CLI structure: `cli/diff.py` grows a `Settings` resolver (flags > env > file >
  defaults) in S5; until then flags keep their current defaults.

## Patterns to mirror

E1: `Redactor` applied once before reporters; golden-file snapshot tests;
sentinel harness; `Frozen` models; CLI flag → config precedence in one
resolver.

## Files to create or change

| File | Action | Why |
|---|---|---|
| `src/permdiff/report/grouping.py` | CREATE | `GroupKey`, `Group`, `group_transitions()`, `sample()` |
| `src/permdiff/report/view.py` | CREATE | `ReportView`: redacted, grouped, sampled structure every reporter consumes |
| `src/permdiff/report/terminal.py` | UPDATE | consume `ReportView` |
| `src/permdiff/report/markdown.py` | CREATE | PR comment |
| `src/permdiff/report/json_.py` | CREATE | envelope `permdiff_report: "1"` |
| `src/permdiff/report/sarif.py` | CREATE | SARIF 2.1.0 |
| `src/permdiff/schemas/report-1.json` | CREATE | JSON report schema, checked in |
| `src/permdiff/config/model.py` | CREATE | `Config` (pydantic) mirroring `permdiff.toml` sections |
| `src/permdiff/config/load.py` | CREATE | file discovery (cwd upward to repo root), env overlay, flag overlay, unknown-key errors |
| `src/permdiff/cli/init.py` | CREATE | `permdiff init` |
| `src/permdiff/cli/diff.py` | UPDATE | `--format`, `--output`, `--group-by`, `--samples`, `--show-attribution`, `--include-decisions`, `--pr-comment`, `--salt`, `--max-groups`, filters |
| `src/permdiff/importers/filters.py` | CREATE | `--since/--until/--tool/--agent/--principal` |
| `tests/golden/*.md, *.json, *.sarif` | CREATE | snapshots |
| `tests/unit/report/test_sarif_schema.py` | CREATE | validates against vendored SARIF 2.1.0 schema (`tests/vendor/sarif-schema-2.1.0.json`) using `jsonschema` (dev dep only) |

## Interfaces

```python
# report/grouping.py
GROUP_FIELDS = ("tool", "resource.type", "agent", "principal", "reason")
class GroupKey(Frozen): cls: TransitionClass; parts: tuple[tuple[str, str], ...]
class Group(Frozen): key: GroupKey; count: int; samples: tuple[Transition, ...]; reasons: tuple[str, ...]
def group_transitions(transitions, *, by: Sequence[str], samples: int) -> tuple[Group, ...]
#   sorted: WIDENING first, then TIGHTENING, CANT_EVALUATE, ATTRIBUTION_CHANGE; within class count desc, key asc
#   samples: first N by call id ascending (deterministic)

# report/view.py
class ReportView(Frozen): header; counts; groups; allow_widening; truncated_groups: int; include_decisions
def build_view(report: Report, *, redactor: Redactor, by, samples, max_groups, show_attribution) -> ReportView

# reporters: uniform signature
def render_terminal(view, *, color: bool) -> str
def render_markdown(view) -> str        # starts with "<!-- permdiff -->"
def render_json(view, *, decisions: Sequence[Transition] | None) -> str
def render_sarif(view, *, policy_path: str) -> str

# config/model.py
class PolicyConfig(Frozen): engine: str = "opa"; path: str = "policy/"; base: str = "origin/main"
class OpaConfig(Frozen): decision: str | None; capabilities: str = "default"; nd_cache: str = ""; version: str = OPA_VERSION; undefined: Literal["deny","error"] = "deny"
class CedarConfig(Frozen): principal: str; action: str; resource: str; approval_annotation: str = "require_approval"
class TracesConfig(Frozen): paths: tuple[str, ...] = (); format: str = "auto"; since: str | None = None
class ReportConfig(Frozen): redact: RedactLevel = SAFE; show_args: tuple[str, ...] = (); samples: int = 3; group_by: tuple[str, ...] = ("tool",); fail_on: FailOn = WIDEN; max_groups: int = 50
class Config(Frozen): policy; opa; cedar; traces; report
def load_config(start: Path, *, env: Mapping[str,str], overrides: Mapping[str, Any]) -> Config
#   env key: PERMDIFF_<SECTION>_<KEY>; unknown TOML key -> ConfigError naming it
```

SARIF layout: one `rule` per `TransitionClass` (`permdiff/widening`, ...); one
`result` per group; `level`: widening→`error`, tightening/cant_evaluate→`warning`,
else `note`; `physicalLocation.artifactLocation.uri` = `<policy_path>/<determining file>`
when the determining id has the form `file:line`, else the first policy file; `region.startLine`;
`logicalLocations` = tool (`kind: function`) and hashed principal (`kind: member`);
`partialFingerprints.primaryLocationLineHash` = sha256 of (class, group key parts);
`properties.security-severity` 8.0 for widening.

## Tasks

1. **E3-S1 grouping** — tests: ordering, determinism, combinable keys, samples cap; terminal uses groups.
2. **E3-S2 markdown** — tests: marker, header SHAs, collapsible sections, byte-identical with fixed salt, size cap, `--pr-comment` refuses `--redact none`, sentinel; golden.
3. **E3-S3 json** — tests: schema validation, `--include-decisions`, sentinel; golden.
4. **E3-S4 sarif** — tests: vendored schema validation, one result per group, locations present, fingerprints stable, sentinel; golden.
5. **E3-S5 config** — tests: precedence matrix (flag > env > file > default), unknown key, `init` refuses overwrite, discovery from subdirectory.
6. **E3-S6 filters** — tests: `--since 7d` relative to newest trace timestamp (not wall clock; documented), ISO bounds, globs, footer counts.

## Test strategy

Golden files per format; sentinel harness on every format; `jsonschema` dev-dependency for
JSON and SARIF schema checks; property test: grouping counts sum to class counts.

## Validation

```bash
uv run pytest tests/unit/report tests/unit/config tests/unit/importers/test_filters.py
uv run permdiff demo --format markdown | head -30
uv run permdiff demo --format sarif > /tmp/p.sarif && uv run python -c "import json;json.load(open('/tmp/p.sarif'))"
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Markdown exceeds GitHub comment limit (65,536 chars) on large diffs | Medium | `--max-groups` default 50, samples 3, truncation note; size test on a large synthetic report |
| `--since 7d` semantics confuse users (relative to newest trace vs now) | Medium | header prints the effective window; documented |
| SARIF upload rejected for missing `region` | Low | always emit `startLine ≥ 1`; schema test; manual upload check in E4 |
| Salt handling: CI needs stable hashes across runs but not across repos | Low | Action passes `--salt` derived from repo id; local default random per run, printed |

## Acceptance

- [x] All six stories done and marked
- [x] Four formats render the demo; goldens committed
- [x] Sentinel test passes for every format
