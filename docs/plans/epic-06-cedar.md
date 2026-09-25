# Plan: E6 — Cedar evaluator

**Source**: [03-epics.md](../03-epics.md) E6; FR-11; NFR-C4
**Complexity**: Medium (2 stories)
**Status**: planned 2026-09-25

## Summary

`pip install permdiff[cedar]` enables `--engine cedar`: policies, schema, and
entities loaded per ref, requests built from configurable templates, batch
evaluation through `cedarpy`, approval via annotation, errors surfaced as
`missing_context`.

## Patterns to mirror

E2's evaluator structure (`options`, `prepare`, `evaluate`, golden corpus); E3 `CedarConfig`.

## Files to create or change

| File | Action | Why |
|---|---|---|
| `src/permdiff/evaluators/cedar/__init__.py` | CREATE | lazy import guard: missing `cedarpy` → `EngineError` with install command |
| `src/permdiff/evaluators/cedar/loader.py` | CREATE | read `*.cedar`, `*.cedarschema`, `entities.json`; validate via `cedarpy.validate_policies` |
| `src/permdiff/evaluators/cedar/request.py` | CREATE | templates → entity uids; context merge; `now` RFC 3339 |
| `src/permdiff/evaluators/cedar/annotations.py` | CREATE | parse policy annotations and ids from source (regex on `@name("...")` before `permit`/`forbid`) |
| `src/permdiff/evaluators/cedar/evaluator.py` | CREATE | `CedarEvaluator` |
| `src/permdiff/demo/policy_*/cedar/` | CREATE | demo variant |
| `tests/fixtures/cedar/` | CREATE | policies, schema, entities; approval mixed case; missing attribute; datetime rule |
| `tests/golden/cedar_demo_transitions.json` | CREATE | NFR-Q3 |

## Interfaces

```python
class CedarOptions(Frozen): principal_tpl: str; action_tpl: str; resource_tpl: str; approval_annotation: str = "require_approval"; now_key: str = "now"
class CedarPrepared(PreparedPolicy): label; policies_text: str; schema_text: str | None; entities_json: str; policy_meta: Mapping[str, PolicyMeta]  # id -> annotations
class CedarEvaluator:
    name = "cedar"
    def prepare(self, policy_dir, *, label) -> CedarPrepared     # validation errors -> EngineError naming file
    def evaluate(self, prepared, calls) -> tuple[Decision, ...]  # cedarpy.is_authorized_batch(requests, policies, entities, schema)
def build_request(call: ToolCall, opts: CedarOptions) -> dict   # {"principal","action","resource","context": {**arguments, **context, "now": iso}}
def decision_from_response(resp, meta, opts, call_id) -> Decision
#   allowed -> ALLOW (determining = reasons)
#   denied: determining forbids all annotated approval -> REQUIRE_APPROVAL; any plain forbid -> DENY; errors non-empty -> error/missing_context (message parsed for attribute/entity)
```

Template syntax: `{principal.id}`, `{tool.name}`, `{resource.type}`, `{resource.id}`,
`{agent.id}`; missing `resource.id` with a template that needs it → `error/missing_context`.

## Tasks

1. **E6-S1 load + evaluate** — tests: extra missing → message; loader errors; templates; context merge and `now`; batch call on 1K fixture; timed 100K `slow` test with the number recorded in README.
2. **E6-S2 approval, errors, attribution, golden** — tests: annotation parsing; mixed forbid; missing attribute → `missing_context` with name; determining ids; golden corpus; demo Cedar variant.

## Test strategy

Tests are skipped with reason when `cedarpy` is not installed; CI installs the extra on
one matrix cell per OS. Confirm `cedarpy` API names against its README at implementation
time (rule 3).

## Validation

```bash
uv sync --extra cedar --dev
uv run pytest tests/unit/evaluators/cedar
uv run permdiff demo --engine cedar
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `cedarpy` batch API shape differs from the researched README | Medium | verify at story start; wrap in one adapter function |
| Annotation parsing by regex mis-attributes on unusual formatting | Medium | run `cedarpy.format_policies` first, then parse; tests with comments and multi-line annotations |
| `cedarpy` has no wheel for a CI platform | Low | skip with reason; document |
| Error messages from Cedar not stable for attribute-name extraction | Medium | best-effort parse; always include raw message in `reasons` |

## Acceptance

- [ ] Both stories done and marked
- [ ] Cedar golden corpus matches; demo Cedar variant runs
