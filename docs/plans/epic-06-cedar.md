# Plan: E6 — Cedar evaluator

**Source**: [03-epics.md](../03-epics.md) E6; FR-11; NFR-C4
**Complexity**: Medium (2 stories)
**Status**: in progress since 2026-09-25 (plan re-read; cedarpy API verified by a spike)

## Summary

`pip install permdiff[cedar]` enables `--engine cedar`: policies, schema, and
entities loaded per ref, requests built from configurable templates, batch
evaluation through `cedarpy`, approval via annotation, errors surfaced as
`missing_context`.

## Verified 2026-09-25 (cedarpy 4.12.1 spike)

- `cedarpy` 4.12.1 is current on PyPI (wheels for cp311–cp312 macOS arm64/x86_64, Linux
  x86_64/aarch64, Windows; cp313/cp314 wheels not listed for macOS, so CI runs the Cedar
  cell on 3.12). Installed via `uv sync --extra cedar --dev`.
- API: `is_authorized_batch(requests, policies, entities, schema=None) -> list[AuthzResult]`
  with `AuthzResult.allowed`, `.decision` (`Decision.Allow|Deny`), `.diagnostics.reasons`
  (policy ids such as `policy0`), `.diagnostics.errors` (strings), and
  `.diagnostics.id_annotations_by_reason` (`@id` values). Requests take Cedar surface syntax
  (`User::"alice"`) or `{"type", "id"}` dicts; entities as a list of
  `{"uid", "attrs", "parents"}`.
- `validate_policies(policies, schema) -> ValidationResult(validation_passed, errors:
  [ValidationError(policy_id, error)], id_annotations_by_policy_id)`. Schema text in Cedar
  schema syntax (`entity User = {...}; action "x" appliesTo {...};`) is accepted directly.
- `policies_to_json_str(policies)` returns `{"staticPolicies": {"policy0": {..., "annotations":
  {"id": "...", "require_approval": "..."}}}}`: annotations and effects come from here, so no
  regex parsing (`annotations.py` is replaced by this JSON).
- Error strings for missing data look like ``error while evaluating policy `policy5`:
  `User::"bob"` does not have the attribute `department` ``; the attribute or entity name is
  extracted best-effort and the raw message is kept in `reasons`.
- Cedar `datetime` extension values are passed in context as
  `{"__extn": {"fn": "datetime", "arg": "2026-09-20T14:00:00Z"}}`; a business-hours rule using
  `context.now.toTime()` flips correctly between 04:00 and 14:00 UTC. `now` is derived from the
  trace timestamp (the replay clock).
- Determining ids: `@id` annotation when present (via `id_annotations_by_reason`), else the
  positional `policyN` id.

## Patterns to mirror

E2's evaluator structure (`options`, `prepare`, `evaluate`, golden corpus); E3 `CedarConfig`.

## Files to create or change

| File | Action | Why |
|---|---|---|
| `src/permdiff/evaluators/cedar/__init__.py` | CREATE | lazy import guard: missing `cedarpy` → `EngineError` with install command |
| `src/permdiff/evaluators/cedar/loader.py` | CREATE | read `*.cedar`, `*.cedarschema`, `entities.json`; validate via `cedarpy.validate_policies` |
| `src/permdiff/evaluators/cedar/request.py` | CREATE | templates → entity uids; context merge; `now` RFC 3339 |
| `src/permdiff/evaluators/cedar/annotations.py` | CREATE | policy effects, ids, and annotations from `policies_to_json_str` (no regex) |
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
