# Plan: E2 — OPA evaluator

**Source**: [03-epics.md](../03-epics.md) E2; FR-10, FR-25; NFR-C3, NFR-S3
**Complexity**: Medium (4 stories)
**Status**: planned 2026-09-25

## Summary

Add `--engine opa`: a pinned `opa` binary run once per ref over the whole
corpus through a generated shim, with per-call time injection, restricted
capabilities, optional recorded nondeterministic-builtin values, and a
configurable result mapping. Add `permdiff check`. Switch `permdiff demo` to
OPA when available.

## Patterns to mirror

From [epic-01-foundation.md](epic-01-foundation.md): `Evaluator`/`PreparedPolicy`
protocols, `_proc.run()` wrapper, `EngineError` messages naming the ref and
builtin, tests-first per story, `slow` marker for the 100K case.

## Files to create or change

| File | Action | Why |
|---|---|---|
| `src/permdiff/evaluators/opa/__init__.py` | CREATE | `OpaEvaluator` registered as `opa` |
| `src/permdiff/evaluators/opa/binary.py` | CREATE | version pin, SHA table, cache dir, download, verify, `resolve_binary()` |
| `src/permdiff/evaluators/opa/shim.py` | CREATE | renders `permdiff_shim.rego` and `cases.json` |
| `src/permdiff/evaluators/opa/capabilities.py` | CREATE | builds the restricted capabilities JSON from `opa capabilities` output minus the denylist |
| `src/permdiff/evaluators/opa/mapping.py` | CREATE | result → `Decision` (object / bool / undefined policy) |
| `src/permdiff/evaluators/opa/ndcache.py` | CREATE | parse OPA `nd_builtin_cache` shape; render `with` overrides |
| `src/permdiff/evaluators/opa/evaluator.py` | CREATE | `prepare()` (compile check via `opa check`), `evaluate()` (one `opa eval`) |
| `src/permdiff/cli/setup.py` | CREATE | `permdiff setup opa [--version]` |
| `src/permdiff/cli/check.py` | CREATE | `permdiff check` |
| `src/permdiff/cli/diff.py` | UPDATE | `--decision`, `--opa-bin`, `--nd-cache`, `--v0-compatible`, `--undefined deny\|error` |
| `src/permdiff/demo/` | UPDATE | add `policy_base/agent.rego`, `policy_head/agent.rego`; demo prefers OPA |
| `tests/fixtures/opa/` | CREATE | policies: basic object decision, boolean, business-hours, `http.send`, undefined cases |
| `tests/golden/opa_demo_transitions.json` | CREATE | golden corpus expectations (NFR-Q3) |
| `README.md` | UPDATE | OPA quickstart |

## Interfaces

```python
# evaluators/opa/binary.py
OPA_VERSION = "1.21.0"
OPA_SHA256: Mapping[tuple[str, str], str]   # (system, machine) -> sha256
def resolve_binary(explicit: Path | None, *, env=os.environ, download: bool = True) -> Path
def download(version: str, dest_dir: Path) -> Path   # verifies sha256, atomic rename

# evaluators/opa/shim.py
SHIM_PACKAGE = "permdiff"
def render_shim(decision_path: str, *, nd_overrides: Sequence[NdOverride] = ()) -> str
#   results := [r | some c in data.permdiff.cases
#                   r := {"id": c.id, "value": <decision_path> with input as c.call
#                                                with time.now_ns as c.ts_ns <nd withs>}]
def render_cases(calls: Sequence[ToolCall]) -> bytes   # {"cases": [{"id","ts_ns","call": <ToolCall JSON>}]}

# evaluators/opa/mapping.py
class UndefinedPolicy(StrEnum): DENY, ERROR
def to_decision(call_id: str, raw: Any, *, undefined: UndefinedPolicy, engine="opa") -> Decision
#   object: {"effect": "allow|deny|require_approval", "reason"?: str, "reasons"?: [str], "rule"?/"rules"?: ids}
#   bool: True->allow False->deny; missing id in results -> undefined policy
#   unknown effect string -> error/unsupported

# evaluators/opa/capabilities.py
DENIED_BUILTINS = ("http.send", "net.lookup_ip_addr", "rand.intn", "uuid.rfc4122", "opa.runtime")
def restricted_capabilities(opa_bin: Path, *, allow: frozenset[str] = frozenset()) -> Path  # cached per version

# evaluators/opa/ndcache.py
class NdOverride(Frozen): builtin: str; table: Mapping[str, Any]   # key = canonical JSON of args
def load_nd_cache(path: Path) -> tuple[NdOverride, ...]

# evaluators/opa/evaluator.py
class OpaOptions(Frozen): decision: str; undefined: UndefinedPolicy = DENY; opa_bin: Path | None = None
                          nd_cache: Path | None = None; v0_compatible: bool = False
class OpaPrepared(PreparedPolicy): label; policy_dir; capabilities_path; compile_ok: bool; compile_error: str | None
class OpaEvaluator:
    name = "opa"
    def __init__(self, options: OpaOptions): ...
    def prepare(self, policy_dir, *, label) -> OpaPrepared      # runs `opa check --capabilities ... policy_dir`
    def evaluate(self, prepared, calls) -> tuple[Decision, ...] # if compile failed: every call error/nondeterministic (if a denied builtin) or error/eval_error
```

`opa eval` invocation: `[opa, "eval", "--format", "json", "--strict-builtin-errors",
"--capabilities", caps, "-b", policy_dir, "-d", shim_path, "-d", cases_path,
"data.permdiff.results"]` plus `--v0-compatible` when set. Output parsed from
`result[0].expressions[0].value`.

## Tasks

1. **E2-S1 binary** — tests: `resolve_binary` precedence (flag > env > cache > download), SHA mismatch raises `EngineError`, download mocked with `urllib` monkeypatch, offline message; action: `binary.py`, `cli/setup.py`.
2. **E2-S2 shim + mapping** — tests: shim renders valid Rego (run `opa check` on it), cases JSON shape, mapping table (object/bool/undefined/unknown), 100K `slow` test < 10 s per ref using the basic fixture; action: `shim.py`, `mapping.py`, `evaluator.py`, CLI flags.
3. **E2-S3 time, capabilities, nd-cache** — tests: business-hours fixture flips between two timestamps; `http.send` fixture → compile failure names `http.send`, all calls `error/nondeterministic`; nd-cache fixture replays recorded values; missing key → error; action: `capabilities.py`, `ndcache.py`, shim `with` rendering.
4. **E2-S4 check + demo** — tests: `permdiff check` exit codes; demo golden transitions with OPA; fallback to Python engine when binary unavailable (monkeypatch); action: `cli/check.py`, demo Rego policies, README.

## Test strategy

- OPA-dependent tests use a session fixture that resolves the binary (download once into
  the uv cache on CI, cached by `actions/cache` keyed on version); skipped with a clear
  reason if unavailable offline.
- Golden expectations checked in; regenerated only with `UPDATE_GOLDEN=1`.
- Capabilities file content asserted against `opa capabilities --current`.

## Validation

```bash
uv run pytest tests/unit/evaluators/opa tests/integration/test_cli_opa.py
uv run pytest -m slow tests/slow/test_opa_100k.py
uv run permdiff demo --engine opa
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `opa` release asset naming or checksum URL changes | Low | pin exact URLs per version in `binary.py`; test resolves the table for current version in CI weekly |
| Comprehension memory for 100K cases with large arguments | Medium | stream `cases.json`; measure RSS in slow test; document `--since` for huge corpora |
| Policies that reference `data.*` documents beyond the policy dir | Medium | `-b policy_dir` loads `data.json`/`data.yaml` in it; document; later flag `--data` |
| `with time.now_ns` not honored inside functions called by the decision rule | Low | verified by OPA docs and local test in research; covered by business-hours fixture |
| Capabilities file omits builtins a policy legitimately needs (e.g., `time.*` ok, `crypto.*`) | Low | denylist only, not allowlist; `[opa] capabilities = path` override |

## Acceptance

- [ ] All four stories done and marked
- [ ] 100K calls per ref under 10 s on the slow test
- [ ] `permdiff demo` uses OPA and matches golden
