# Plan: E11 — `--input-map` for foreign OPA decision-log inputs

**Source**: [03-epics.md](../03-epics.md) E11; FR-L4 follow-on (decisions.md 2026-09-26)
**Complexity**: Small (2 stories, about half a day)
**Status**: in progress 2026-09-26 (S1 done)

## Summary

Let `--from opa-decision-log` build a `ToolCall` from any `input` shape through declared
`target=source` pairs, defaulting `id` and `timestamp` from the event. Everything else in
E10 (result mapping, context, nd-cache) stays as is.

## Verified 2026-09-26

- E10's importer takes `decision` through the registry's signature-based option filter
  (`registry._accepted`); adding `input_map` to the constructor is enough for plumbing.
- Config tuples parse from env as comma-separated (`config/load.py:_coerce_env`), render
  as TOML arrays (`config/write.py`), and CLI flags become overrides via
  `settings.CONFIG_FLAGS` + `overrides_from` (`show_args` is the tuple precedent).
- `TracesConfig` is a frozen pydantic model with `principal_from` as the last importer
  option; `settings.py` builds `importer_options` from it (lines ~300).

## Patterns to mirror

| Category | Source | Pattern |
|---|---|---|
| Option parsing | `cli/settings.py` `_split`, `CONFIG_FLAGS`, `overrides_from` | comma-split tuple flags backed by config |
| Config errors | `permdiff.errors.ConfigError` | name the offending value |
| Path lookup | `demo/engine.lookup` | dotted-path resolution over mappings/attributes |
| Tests | `tests/unit/importers/test_opa_log.py`, `tests/integration/test_cli_config.py` | fixture events; config/env/flag precedence |

## Files to create or change

| File | Action | Why |
|---|---|---|
| `src/permdiff/importers/input_map.py` | CREATE | `InputMap`, `parse_input_map`, `TARGETS`, `resolve_source`, `apply` |
| `src/permdiff/importers/opa_log.py` | UPDATE | `input_map` option; use `InputMap.apply` before validation |
| `src/permdiff/config/model.py`, `config/write.py` | UPDATE | `traces.input_map: tuple[str, ...]` with a comment line |
| `src/permdiff/cli/settings.py`, `cli/convert.py` | UPDATE | `--input-map` (multiple), override key, importer option |
| `tests/unit/importers/test_input_map.py`, `test_opa_log.py` | CREATE/UPDATE | AC-L4.10 to AC-L4.12 |
| `tests/integration/test_cli_convert.py`, `test_cli_config.py` | UPDATE | flag, env, and config paths |
| `docs/importers.md`, `CHANGELOG.md`, `docs/03-epics.md` | UPDATE | worked example, entry, statuses |

## Interfaces

```python
# importers/input_map.py
CONST_PREFIX = "const:"; EVENT_PREFIX = "event."
FIXED_TARGETS = {"id","timestamp","principal.id","principal.type","agent.id","agent.version","tool.name","tool.server","tool.type","arguments","resource.type","resource.id"}
PREFIX_TARGETS = ("principal.attrs.", "agent.attrs.", "arguments.", "resource.attrs.", "context.")
class InputMap(Frozen): pairs: tuple[tuple[str, str], ...]
def parse_input_map(specs: Iterable[str]) -> InputMap        # ConfigError on bad pair
def resolve_source(source: str, *, input: Any, event: Mapping) -> Any   # None when absent
def apply(input_map: InputMap, *, input: Any, event: Mapping) -> dict[str, Any]   # nested ToolCall payload with defaults
```

## Tasks

1. **S1** tests first: parse (valid, unknown target, empty side, duplicate, comma-joined),
   resolve (`a.b`, list index, `event.`, `const:`, absent), apply (defaults, nested
   attrs, arguments object vs key, absent required → reason); importer test mapping the
   fixture's foreign event.
2. **S2** tests first: `convert --input-map` on the fixture imports 4 calls; config
   `traces.input_map` and `PERMDIFF_TRACES_INPUT_MAP` reach the importer via `check`;
   docs; CHANGELOG; statuses.

## Validation

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q
uv run permdiff convert --from opa-decision-log tests/fixtures/opa_log/sink.json --input-map principal.id=const:anonymous --input-map agent.id=const:gateway --input-map tool.name=method --input-map resource.id=path
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Mapping syntax too weak for nested or computed values | Medium | `const:` and dotted paths cover the common shapes; `permdiff convert` output can be post-processed; a richer expression language is deliberately out |
| A map silently mislabels fields | Low | unknown targets are errors; the report header shows the importer and counts skipped events with reasons |

## Acceptance

- [ ] Both stories done and marked in `docs/03-epics.md`
- [ ] Validation passes; CI green
- [ ] The fixture's foreign event imports with a four-pair map
