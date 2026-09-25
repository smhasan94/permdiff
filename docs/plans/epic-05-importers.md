# Plan: E5 — Importers: Custody, OTel, convert

**Source**: [03-epics.md](../03-epics.md) E5; FR-3, FR-4, FR-5, FR-7
**Complexity**: Medium (4 stories)
**Status**: planned 2026-09-25

## Summary

Add Custody `custody.trace.v1` and OpenTelemetry GenAI `execute_tool` span
importers, format auto-detection, and `permdiff convert`.

## Patterns to mirror

E1 `Importer` protocol, `ImportResult`/`ImportStats`, limits guards, locator-bearing
errors, fixtures per variant.

## Files to create or change

| File | Action | Why |
|---|---|---|
| `src/permdiff/importers/custody.py` | CREATE | Custody importer |
| `src/permdiff/importers/otel/__init__.py` | CREATE | `OtelImporter` |
| `src/permdiff/importers/otel/anyvalue.py` | CREATE | OTLP `AnyValue` decoding |
| `src/permdiff/importers/otel/spans.py` | CREATE | walk `resourceSpans → scopeSpans → spans`; index by span id; parent lookup |
| `src/permdiff/importers/otel/mapping.py` | CREATE | attribute → `ToolCall` incl. aliases, `--principal-from` |
| `src/permdiff/importers/registry.py` | UPDATE | register both; `detect()` order: permdiff, custody, otel |
| `src/permdiff/cli/convert.py` | CREATE | `permdiff convert` |
| `tests/fixtures/custody/*.jsonl` | CREATE | one event per `action.type`, per `verdict`, digest-only, unknown schema |
| `tests/fixtures/otel/*.json, *.jsonl` | CREATE | OTLP/JSON and JSONL, from semconv examples; parent chat span with `tool_call` parts; MCP `tools/call`; deprecated names |
| `docs/importers.md` | CREATE | mapping tables (from overview §3.2), caveats |

## Interfaces

```python
# importers/custody.py
CUSTODY_SCHEMA = "custody.trace.v1"
VERDICT_MAP = {"allow": ALLOW, "block": DENY, "warn": ALLOW, "observe": ALLOW}   # warn/observe add a note in Source.locator? no: in Recorded via reasons later; v0.1: effect only + counted note
class CustodyImporter: name = "custody"; detect(head) -> b'"schema"' and b'custody.trace.v1' in head; read(...)

# importers/otel/anyvalue.py
def decode(v: Mapping[str, Any]) -> Any   # stringValue/boolValue/intValue(str->int)/doubleValue/arrayValue/kvlistValue/bytesValue
def attrs(span_attrs: Sequence[Mapping]) -> dict[str, Any]

# importers/otel/mapping.py
TOOL_OPERATION = "execute_tool"
ALIASES = {"gen_ai.system": "gen_ai.provider.name"}
def is_tool_span(span, attrs) -> bool     # op == execute_tool or name startswith "execute_tool " / "tools/call "
def to_toolcall(span, attrs, resource_attrs, *, parent: Span | None, principal_from: str | None, locator) -> ToolCall | None
#   arguments: attrs["gen_ai.tool.call.arguments"] (str -> json.loads, kvlist -> dict) else parent gen_ai.output.messages tool_call by id
#   principal: enduser.id | user.id | resource enduser.id | user.id | principal_from | "unknown" (+ note)
#   id: gen_ai.tool.call.id | spanId ; timestamp: startTimeUnixNano
class OtelImporter: name = "otel"; detect(head) -> b'"resourceSpans"' in head
```

`permdiff convert --from custody|otel FILE... -o out.jsonl`: writes canonical JSONL;
`--strict` as in FR-2.

## Tasks

1. **E5-S1 custody** — tests per AC-3.x; fixture set; docs note "spec-derived".
2. **E5-S2 otel core** — tests: AnyValue table, span walk both file shapes, tool span detection, mapping, `--principal-from`, unknown-principal note.
3. **E5-S3 otel fallback + aliases** — tests: parent `tool_call` lookup by id (string JSON and kvlist), deprecated attrs, MCP spans, missing args → `arguments=None`.
4. **E5-S4 detect + convert** — tests: detection order and mismatch error; convert round-trip equality on canonical fields.

## Test strategy

Fixtures are hand-built from the current spec documents and committed with a `SOURCE`
comment (URL, date). Property test: any `ToolCall` → JSONL → convert → equal.

## Validation

```bash
uv run pytest tests/unit/importers
uv run permdiff convert --from otel tests/fixtures/otel/execute_tool.jsonl -o /tmp/o.jsonl && uv run permdiff check --traces /tmp/o.jsonl --engine python:permdiff.demo.engine:evaluate --policy src/permdiff/demo/policy_base --head WORKTREE --base WORKTREE
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| OTel GenAI conventions rename attributes again | High | alias table; importer versioned; test fixtures carry spec date |
| Real Custody output differs from PLAN.md §5 | High | documented; fixtures marked spec-derived; importer tolerant of extra fields (`extra="ignore"` at the source boundary only) |
| Arguments absent in most real OTel data (Opt-In) | High | fallback to parent span; clear "can't evaluate: arguments not recorded" attribution |
| Principal absent in OTel | High | `--principal-from`; `unknown` principal with a header note |

## Acceptance

- [ ] All four stories done and marked
- [ ] `permdiff diff --from otel` and `--from custody` run on fixtures end to end
