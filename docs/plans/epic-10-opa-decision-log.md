# Plan: E10 — OPA decision-log importer

**Source**: [03-epics.md](../03-epics.md) E10; FR-L4 (scoped 2026-09-26)
**Complexity**: Small (3 stories, about one day)
**Status**: reviewed 2026-09-26 (code-review low: 1 finding fixed, dead except branch in the console line loop)

## Summary

Read OPA decision logs (remote-sink JSON arrays and console log lines) as `ToolCall`
corpora when the deployment's `input` is permdiff-shaped, keep the recorded verdict from
`result`, and let `convert --nd-cache-out` merge the events' `nd_builtin_cache` into the
file `--nd-cache` already accepts. Foreign `input` shapes are skipped with a reason, never
guessed.

## Verified 2026-09-26 (re-read before starting)

- **Event fields** (docs `management-decision-logs`; live OPA 1.21.0): `decision_id`,
  `path` (slash-separated rule path, no `data.` prefix), `input`, `result`, `timestamp`
  (RFC 3339 nanoseconds), `labels` (`id`, `version`, custom), `requested_by`, optional
  `bundles` (`{name: {revision}}`), `erased`, `masked` (JSON-pointer lists),
  `nd_builtin_cache` (`{builtin: {"<json args>": value}}`, `{}` when empty), `metrics`,
  `req_id`. Console lines add `msg: "Decision Log"`, `type:
  "openpolicyagent.org/decision_logs"`, `level`, `time`, and sit among other log lines.
- **`result` shapes** seen live: the decision object when `path` is the rule
  (`agent/authz/decision` → `{"effect": ...}`), the package object when `path` is the
  package (`agent/authz` → `{"decision": {...}, "lucky": 4}`), a scalar for other rules.
- **Existing code**: `evaluators/opa/mapping.to_decision(call_id, raw)` maps a result
  value to a `Decision` (object with `effect`, bool, string; else an `unsupported` error);
  `evaluators/opa/ndcache.load_nd_cache` accepts a single event or a bare cache and
  canonicalizes keys with `canonical_key`; `importers/otel/spans.iter_spans` shows the
  "one JSON document or JSONL" reading pattern; `read_lines` handles per-line skip/abort.
- **Capture**: `scratchpad/opa-decision-log-1.21.0.jsonl` (four events: allow,
  require_approval, a scalar `lucky` result with `rand.intn` cached, and a foreign input
  with a package-object result). Config: `decision_logs.console: true`,
  `nd_builtin_cache: true`.

## Patterns to mirror

| Category | Source | Pattern |
|---|---|---|
| Module layout | `src/permdiff/importers/custody.py` | constants, `to_toolcall(event, locator)`, class with `name`, `detect`, `read` |
| Two file shapes | `src/permdiff/importers/otel/spans.py` | parse the whole file as JSON first (array), else line by line |
| Result mapping | `src/permdiff/evaluators/opa/mapping.py:to_decision` | reuse; `Decision.effect` becomes `recorded.effect`, error → unset plus reason |
| Nd cache | `src/permdiff/evaluators/opa/ndcache.py` | `canonical_key`; output file is the bare `{builtin: {args: value}}` shape |
| Validation reasons | `importers/jsonl.summarize_validation_error` | first error's location and message |
| Convert extension | `src/permdiff/cli/convert.py` | one more option, one more summary line |
| Tests | `tests/unit/importers/test_custody.py`, `tests/integration/test_cli_opa.py` | fixture files with a README; OPA integration tests are marked and skip without the binary |

## Files to create or change

| File | Action | Why |
|---|---|---|
| `src/permdiff/importers/opa_log.py` | CREATE | `OpaDecisionLogImporter`, `iter_events`, `to_toolcall`, `recorded_from_result`, `ND_CACHE_CONTEXT_KEY` |
| `src/permdiff/importers/registry.py` | UPDATE | register after the Claude Code importers; pass `decision` option |
| `src/permdiff/evaluators/opa/ndcache.py` | UPDATE | `merge_nd_caches(calls) -> (NdCache, conflicts)` and `render_nd_cache_file` |
| `src/permdiff/cli/convert.py` | UPDATE | `--nd-cache-out PATH`; conflict report; `--strict` aborts on conflict |
| `src/permdiff/cli/settings.py` | UPDATE | pass `opa.decision` to importers as `decision` (registry ignores it elsewhere via `TypeError` fallback) |
| `src/permdiff/api.py` | UPDATE | `load_traces` accepts `decision` in `importer_options` (no change if it already forwards a mapping) |
| `tests/fixtures/opa_log/console.jsonl`, `sink.json`, `README.md` | CREATE | the capture (scrubbed `labels.id`, `requested_by`) and the same events as an array |
| `tests/unit/importers/test_opa_log.py` | CREATE | per-AC tests |
| `tests/unit/evaluators/opa/test_ndcache.py` | UPDATE | merge and conflict tests |
| `tests/integration/test_cli_convert.py` | UPDATE | `--nd-cache-out` writes a loadable cache; conflict reporting |
| `tests/integration/test_cli_opa.py` | UPDATE | replay the console fixture with `--engine opa --nd-cache` (marked, skips without the binary) |
| `docs/importers.md`, `README.md` (one line), `CHANGELOG.md`, `docs/03-epics.md` | UPDATE | docs and statuses |

## Interfaces

```python
# importers/opa_log.py
FORMAT_NAME = "opa-decision-log"
EVENT_TYPE = "openpolicyagent.org/decision_logs"
ND_CACHE_CONTEXT_KEY = "opa.nd_builtin_cache"      # per-call copy of the event's cache

def is_event(obj: Any) -> bool                    # Mapping with type == EVENT_TYPE, or decision_id and input
def iter_events(path: Path) -> Iterator[tuple[Mapping, str]]   # (event, locator): array → "path[i]", lines → "path:lineno"; non-event lines skipped
def unwrap_result(result: Any, decision: str | None) -> Any    # package object → value under the rule's last segment when present
def recorded_from_result(call_id: str, result: Any) -> tuple[Effect | None, str | None]   # via to_decision; error → (None, reason)
def to_toolcall(event: Mapping, locator: str, *, decision: str | None) -> ToolCall
#   input must be a Mapping → ToolCall.model_validate(input) else RecordRejected("input is not a permdiff ToolCall: <first error>")
#   context adds: opa.decision_id, opa.path, opa.logged_at, opa.labels (mapping), opa.bundles ({name: revision}),
#                 opa.requested_by, opa.erased, opa.masked, opa.result_unmapped, opa.nd_builtin_cache (when non-empty)
#   recorded: effect from result; policy_hash = the single bundle revision when exactly one bundle
#   source: {"format": FORMAT_NAME, "locator": locator}
class OpaDecisionLogImporter:
    name = FORMAT_NAME
    def __init__(self, decision: str | None = None)
    def detect(self, head) -> bool      # first non-blank line: an event, or "[" followed by an object with decision_id/input
    def read(self, path, *, strict, max_records) -> ImportResult

# evaluators/opa/ndcache.py
class NdConflict(Frozen): builtin: str; args: str; kept: Any; dropped: Any; kept_from: str; dropped_from: str
def merge_nd_caches(calls: Sequence[ToolCall]) -> tuple[NdCache, tuple[NdConflict, ...]]
def render_nd_cache_file(cache: NdCache) -> str   # pretty JSON, bare shape

# cli/convert.py
--nd-cache-out PATH   # "merged nd_builtin_cache from N events into PATH (K builtins, C conflicts)"
```

## Tasks

1. **E10-S1 importer** — tests first from the fixture: array and console forms give the
   same three calls; the foreign-input event is skipped with "input is not a permdiff
   ToolCall: principal: field required"; recorded effects `allow`, `require_approval`,
   unset for the scalar result with `opa.result_unmapped`; `--decision
   data.agent.authz.decision` unwraps a package object; context keys; `policy_hash` from a
   single bundle; detection order and `--from` mismatch. Then implement and register.
2. **E10-S2 nd-cache merge** — tests: merge two calls' caches; conflict keeps the first
   and reports both decision ids; `render` output loads through `load_nd_cache`; convert
   integration test writes the file and prints the summary; strict aborts on conflict;
   OPA integration test replays the fixture with `--nd-cache` (marked `opa`).
3. **E10-S3 docs** — fixture README with the config and OPA version; importer docs
   section with the mapping table and the `input`-shape caveat; README one-liner in the
   importer list; CHANGELOG; statuses.

## Test strategy

Fixtures are the live capture, scrubbed (`labels.id`, `requested_by`, `metrics` kept as
captured since they carry nothing sensitive). Unit tests per AC; the OPA replay test runs
only where the pinned binary is cached (same marker as `tests/integration/test_cli_opa.py`).

## Validation

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -q tests/unit/importers/test_opa_log.py tests/unit/evaluators/opa/test_ndcache.py tests/integration/test_cli_convert.py tests/integration/test_cli_opa.py
uv run permdiff convert --from opa-decision-log tests/fixtures/opa_log/console.jsonl --nd-cache-out /tmp/nd.json
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Real deployments send a foreign `input` shape | High | skipped with a named reason and a counted total; docs point to `--input-map` as the later story |
| `result` is a package object and `--decision` is not given | Medium | effect stays unset with `opa.result_unmapped`; header note counts them; docs say to pass `--decision` |
| Console logs mix in non-event lines and partial writes | Medium | non-events skipped silently; a bad JSON line is skipped and counted (strict aborts) |
| Conflicting `nd_builtin_cache` values across events | Low | first wins, every conflict reported with both decision ids; `--strict` aborts |
| Sink payloads are gzip on the wire | Low | out of scope: users gunzip first; detect says so when the head starts with the gzip magic |

## Acceptance

- [ ] All three stories done and marked in `docs/03-epics.md`
- [ ] Validation passes; CI (`ci`, `bench`, `dogfood`) green
- [ ] The captured log replays with `--engine opa --nd-cache` and `rand.intn` resolves
- [ ] Patterns mirrored: `to_decision`, `canonical_key`, `iter_spans`, fixture README
