# Plan: E1 — Foundation

**Source**: [03-epics.md](../03-epics.md) E1, [02-prd.md](../02-prd.md)
**Complexity**: Large (10 stories, sets every convention)
**Status**: reviewed 2026-09-25 (code-review low: 3 findings fixed)

## Summary

Deliver an installable `permdiff` package whose `permdiff demo` prints a real
transition report using the Python callable engine, and whose `permdiff diff`
works on a real git repo with a Python policy. Establish the package layout,
model conventions, test harness, and CI that every later epic mirrors.

## Patterns to mirror

No code exists yet. This plan defines the patterns; later plans cite this
file. Conventions chosen:

| Category | Convention |
|---|---|
| Layout | `src/permdiff/<area>/` packages; one concept per module; files under 400 lines |
| Naming | modules `snake_case`; classes `PascalCase`; constants `UPPER_SNAKE`; booleans `is_/has_/should_` |
| Models | `pydantic.BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`; tuples not lists in frozen models; never mutate, always `model_copy(update=...)` |
| Errors | one exception hierarchy in `permdiff/errors.py`: `PermdiffError` → `ImportError_`, `PolicyError`, `EngineError`, `ConfigError`, `GateFailedError`; every message names file/line/ref/flag; CLI maps to exit codes in one place |
| Logging | stdlib `logging`, logger per module (`logging.getLogger(__name__)`); `--verbose` = INFO, `--debug` = DEBUG; never `print` outside reporters |
| Subprocess | `subprocess.run([...], check=False, capture_output=True, text=True)`; argument lists only; wrapper in `permdiff/_proc.py` |
| Tests | `tests/unit/<area>/test_<module>.py`, `tests/integration/`, `tests/slow/` (marker `slow`, skipped by default); AAA structure; names `test_<behavior>_when_<condition>`; fixtures in `tests/conftest.py`; golden files in `tests/golden/` |
| Typing | `mypy --strict`; `from __future__ import annotations`; `Protocol` for plugin interfaces |

## Files to create

| File | Purpose |
|---|---|
| `pyproject.toml` | hatchling build; deps `click>=8.1`, `rich>=13`, `pydantic>=2.7`; extra `cedar = ["cedarpy~=4.12"]`; scripts `permdiff = "permdiff.cli.main:cli"`; entry-point groups `permdiff.evaluators`, `permdiff.importers`; ruff, mypy, pytest, coverage config |
| `uv.lock` | lock file |
| `LICENSE` | Apache-2.0 |
| `README.md` | description, install, quickstart (kept working every story) |
| `.github/workflows/ci.yml` | lint, types, tests (3.11–3.14 × ubuntu, macos), coverage gate 80%, quickstart script |
| `scripts/quickstart_check.sh` | runs README commands in a clean venv (NFR-Q5) |
| `src/permdiff/__init__.py` | public API re-exports, `__version__` |
| `src/permdiff/errors.py` | exception hierarchy |
| `src/permdiff/_proc.py` | subprocess wrapper |
| `src/permdiff/models/toolcall.py` | `Principal`, `Agent`, `Tool`, `Resource`, `Recorded`, `Source`, `ToolCall` |
| `src/permdiff/models/decision.py` | `Effect`, `ErrorKind`, `Decision` |
| `src/permdiff/models/transition.py` | `TransitionClass`, `Transition`, `classify()` |
| `src/permdiff/models/report.py` | `ReportHeader`, `Counts`, `Report` |
| `src/permdiff/models/limits.py` | `MAX_LINE_BYTES`, `MAX_NESTING`, `DEFAULT_MAX_RECORDS` |
| `src/permdiff/schemas/__init__.py` | `json_schema(name)` from models; `permdiff schema` uses it |
| `src/permdiff/importers/base.py` | `Importer` protocol, `ImportStats`, `ImportResult` |
| `src/permdiff/importers/registry.py` | built-in list + entry points, `detect()`, `get()` |
| `src/permdiff/importers/jsonl.py` | permdiff JSONL importer |
| `src/permdiff/importers/limits.py` | line/nesting guards shared by importers |
| `src/permdiff/evaluators/base.py` | `Evaluator`, `PreparedPolicy` protocols |
| `src/permdiff/evaluators/registry.py` | `resolve(engine_spec)` incl. `python:mod:fn` and entry points |
| `src/permdiff/evaluators/python_callable.py` | `PythonCallableEvaluator` |
| `src/permdiff/policy/source.py` | `PolicySource`, `GitRefSource`, `WorktreeSource`, `MaterializedPolicy` |
| `src/permdiff/policy/git.py` | `rev_parse`, `archive_to` helpers |
| `src/permdiff/replay/runner.py` | `replay(calls, evaluator, base, head) -> ReplayResult` |
| `src/permdiff/redact/redactor.py` | `RedactLevel`, `Redactor`, placeholder rules, principal hashing |
| `src/permdiff/report/terminal.py` | terminal reporter (rich) |
| `src/permdiff/report/exit_codes.py` | `EXIT_OK`, `EXIT_TOOL_ERROR`, `EXIT_GATE`, `FailOn`, `gate()` |
| `src/permdiff/cli/main.py` | click group, global options, error → exit code mapping |
| `src/permdiff/cli/diff.py` | `permdiff diff` |
| `src/permdiff/cli/demo.py` | `permdiff demo` |
| `src/permdiff/cli/schema.py` | `permdiff schema` |
| `src/permdiff/api.py` | `load_traces()`, `diff()` |
| `src/permdiff/demo/corpus.jsonl` | 200 synthetic calls |
| `src/permdiff/demo/policy_base/rules.py`, `policy_head/rules.py` | rule tables |
| `src/permdiff/demo/engine.py` | `evaluate(call, policy_dir)` reading `rules.py` |
| `tests/conftest.py` | `git_repo` (two commits), `sentinel_corpus`, `sample_call`, `tmp_policy_dir` |
| `tests/unit/...`, `tests/integration/test_cli_diff.py`, `tests/slow/test_jsonl_100k.py` | per story |
| `docs/schemas/` | not needed; schemas generated into the wheel at build via `hatch` build hook or checked in under `src/permdiff/schemas/*.json` (choose: checked in, regenerated by `permdiff schema --write`, CI asserts no drift) |

## Interfaces

```python
# models/toolcall.py
class Principal(Frozen): id: str; type: str = "user"; attrs: Mapping[str, Any] = {}
class Agent(Frozen):     id: str; version: str | None = None; attrs: Mapping[str, Any] = {}
class Tool(Frozen):      name: str; server: str | None = None; type: str | None = None
class Resource(Frozen):  type: str | None = None; id: str | None = None; attrs: Mapping[str, Any] = {}
class Recorded(Frozen):  effect: Effect | None = None; policy_hash: str | None = None
class Source(Frozen):    format: str; locator: str
class ToolCall(Frozen):
    id: str; timestamp: datetime (tz-aware, validated); principal: Principal; agent: Agent
    tool: Tool; arguments: Mapping[str, Any] | None = None; resource: Resource = Resource()
    context: Mapping[str, Any] = {}; recorded: Recorded = Recorded(); source: Source | None = None
    @classmethod def derived_id(cls, timestamp, principal_id, tool_name, arguments) -> str

# models/decision.py
class Effect(StrEnum): ALLOW, DENY, REQUIRE_APPROVAL, ERROR
class ErrorKind(StrEnum): MISSING_CONTEXT, NONDETERMINISTIC, EVAL_ERROR, UNSUPPORTED
class Decision(Frozen):
    call_id: str; effect: Effect; error_kind: ErrorKind | None = None
    reasons: tuple[str, ...] = (); determining: tuple[str, ...] = (); engine: str
    @classmethod def error(cls, call_id, kind, reason, engine) -> Decision
    @classmethod def from_effect(cls, effect: Effect | str, *, call_id, engine, reasons=()) -> Decision
EFFECT_ORDER = {DENY: 0, REQUIRE_APPROVAL: 1, ALLOW: 2}

# models/transition.py
class TransitionClass(StrEnum): WIDENING, TIGHTENING, ATTRIBUTION_CHANGE, CANT_EVALUATE, UNCHANGED
def classify(base: Decision, head: Decision) -> TransitionClass
class Transition(Frozen): call: ToolCall; base: Decision; head: Decision; cls: TransitionClass

# models/report.py
class ReportHeader(Frozen): base_label, base_sha, head_label, head_sha, is_worktree, policy_path,
                            engine, window: tuple[datetime, datetime] | None, salt: str,
                            undefined_policy: str | None, generated_at
class Counts(Frozen): imported, skipped, filtered, evaluated, by_class: Mapping[TransitionClass, int],
                      recorded_disagreements: int
class Report(Frozen): header; transitions: tuple[Transition, ...]; counts: Counts;
                      allow_widening: tuple[str, str] | None   # (reason, actor)

# importers/base.py
class ImportStats(Frozen): read: int; skipped: int; skipped_locators: tuple[str, ...]
class ImportResult(Frozen): calls: tuple[ToolCall, ...]; stats: ImportStats
class Importer(Protocol):
    name: str
    def detect(self, head: bytes) -> bool: ...
    def read(self, path: Path, *, strict: bool = False, max_records: int = ...) -> ImportResult: ...

# evaluators/base.py
class PreparedPolicy(Protocol):
    label: str
    def close(self) -> None: ...
class Evaluator(Protocol):
    name: str
    def prepare(self, policy_dir: Path, *, label: str) -> PreparedPolicy: ...
    def evaluate(self, prepared: PreparedPolicy, calls: Sequence[ToolCall]) -> tuple[Decision, ...]: ...
# evaluators/registry.py
def resolve(engine_spec: str, **options) -> Evaluator   # "python:pkg.mod:fn" | "opa" | "cedar" | entry point

# policy/source.py
class MaterializedPolicy(Frozen): path: Path; sha: str | None; label: str; is_worktree: bool
class PolicySource(Protocol):
    label: str
    def materialize(self) -> AbstractContextManager[MaterializedPolicy]: ...
class GitRefSource(PolicySource): def __init__(self, repo: Path, ref: str, policy_path: str)
class WorktreeSource(PolicySource): def __init__(self, repo: Path, policy_path: str)
def source_for(repo: Path, ref: str, policy_path: str) -> PolicySource   # "WORKTREE" special-cases

# replay/runner.py
class ReplayResult(Frozen): transitions: tuple[Transition, ...]; counts: Counts
def replay(calls, evaluator, base: MaterializedPolicy, head: MaterializedPolicy,
           *, concurrent: bool = True) -> ReplayResult

# redact/redactor.py
class RedactLevel(StrEnum): SAFE, NONE
class Redactor:
    def __init__(self, level, salt: bytes, show_args: frozenset[str] = frozenset(), show_principal: bool = False)
    def call(self, call: ToolCall) -> ToolCall           # returns a redacted copy
    def principal_hash(self, principal_id: str) -> str   # "principal:3f9a1c2e"
    def value(self, v: Any) -> Any                       # "<str:12>", "<int>", nested mappings keep keys

# report/exit_codes.py
EXIT_OK, EXIT_TOOL_ERROR, EXIT_GATE = 0, 1, 2
class FailOn(StrEnum): WIDEN, ANY_CHANGE, CANT_EVALUATE, NONE
def gate(report: Report, fail_on: FailOn) -> int

# api.py
def load_traces(paths: Sequence[str | Path], *, fmt: str = "auto", strict=False) -> ImportResult
def diff(*, traces: Sequence[ToolCall], base: str, head: str, policy: str, engine: str,
         repo: Path = Path("."), engine_options: Mapping[str, Any] = {}, salt: bytes | None = None) -> Report
```

`Frozen` is a shared base: `class Frozen(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid")`.

## Tasks (sequenced)

### Task 1: E1-S1 skeleton
- Action: `pyproject.toml`, `uv.lock`, `LICENSE`, `README.md`, `src/permdiff/__init__.py`
  (version `0.1.0.dev0`), `errors.py`, `_proc.py`, CI workflow, `scripts/quickstart_check.sh`
  (initially just `permdiff --version`), `tests/conftest.py` stub.
- Validate: `uv sync --all-extras --dev && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` green; `uv run permdiff --version` prints version.

### Task 2: E1-S2 models and schema
- Tests first: `tests/unit/models/test_toolcall.py` (required fields, tz-aware timestamp,
  extra fields rejected, `derived_id` stable), `test_decision.py`, Hypothesis strategy
  `tests/strategies.py` for `ToolCall` round-trip; `tests/unit/schemas/test_schema.py`
  asserts checked-in JSON matches generated.
- Action: models, `schemas/`, `permdiff schema` command, checked-in `*.json`.
- Validate: tests green; `permdiff schema toolcall | python -m json.tool`.

### Task 3: E1-S3 JSONL importer
- Tests first: valid file, malformed line (strict vs skip with locator), non-UTF-8, oversize
  line, nesting depth, max records; `tests/slow/test_jsonl_100k.py` (generate to tmp, < 20 s).
- Action: `importers/base.py`, `limits.py`, `jsonl.py`, `registry.py` (entry points via
  `importlib.metadata.entry_points(group="permdiff.importers")`).
- Validate: tests; `uv run pytest -m slow tests/slow/test_jsonl_100k.py`.

### Task 4: E1-S4 evaluator protocol and Python callable
- Tests first: resolve `python:mod:fn` from a fixture module in `tests/fixtures/py_engine/`;
  string coercion; exception → `error/eval_error`; `verify_deterministic` detects a
  fixture that flips on second call; missing module error names the spec.
- Action: `evaluators/base.py`, `registry.py`, `python_callable.py`.

### Task 5: E1-S5 git policy loading
- Tests first: `git_repo` fixture builds a repo with `policy/rules.py` at two commits;
  materialize each ref, assert content and SHA; WORKTREE picks up an uncommitted change;
  invalid ref raises `PolicyError` with git's message; ref `--upload-pack=x` rejected
  before git runs; temp dir removed after exception; works from a subdirectory.
- Action: `policy/git.py`, `policy/source.py`.

### Task 6: E1-S6 replay and classification
- Tests first: `test_classify.py` table over all `Effect` pairs × error kinds (16 + error
  rows) with expected class; property: every call yields exactly one transition; counts
  sum; recorded disagreement counter; attribution change detection.
- Action: `models/transition.py`, `replay/runner.py` (ThreadPoolExecutor with two
  workers when `concurrent`).

### Task 7: E1-S7 redaction
- Tests first: placeholders for str/int/float/bool/null/list/dict; keys kept; nested;
  principal hash stable for same salt, different across salts; `show_args`; sentinel
  harness `tests/redaction_harness.py` exposing `assert_no_sentinels(text)`; the
  `sentinel_corpus` fixture seeds unique strings in args, attrs, context, principal id.
- Action: `redact/redactor.py`.

### Task 8: E1-S8 terminal reporter and exit codes
- Tests first: snapshot of summary block for a fixed report (golden file); `--no-color`
  and `NO_COLOR`; `gate()` for every `FailOn`; `allow_widening` recorded; sentinel check
  on terminal output.
- Action: `report/terminal.py`, `report/exit_codes.py`.

### Task 9: E1-S9 CLI and API
- Tests first: `tests/integration/test_cli_diff.py` with `click.testing.CliRunner` on the
  `git_repo` fixture and a JSONL corpus: exit codes 0/2/1 cases, `--verbose` timings,
  `--debug` keeps dirs, error messages name flags; `tests/unit/test_api.py`.
- Action: `cli/main.py`, `cli/diff.py`, `api.py`, `__init__.py` exports; `py.typed`.

### Task 10: E1-S10 demo and quickstart
- Tests first: `permdiff demo` exit code 2 and summary counts match golden; `--format`
  accepted values (terminal only for now); demo corpus contains no sentinel strings and
  no realistic PII.
- Action: `demo/` package data (include via `[tool.hatch.build]`), `cli/demo.py`, README
  quickstart, `scripts/quickstart_check.sh` runs `pip install .` in a fresh venv then
  `permdiff demo`; CI job runs it.
- Validate: clean venv install + `permdiff demo` under 5 s.

## Test strategy

- Unit tests per module, AAA, one behavior per test.
- Hypothesis for model round-trips and classification properties.
- Golden files for reporter output; regenerate with `UPDATE_GOLDEN=1`.
- Sentinel harness shared by all reporters (used again in E3).
- Integration via `CliRunner` on a real temp git repo.
- `slow` marker for the 100K test; run in CI on one matrix cell.
- Coverage gate 80% (`--cov-fail-under=80`).

## Validation

```bash
uv sync --all-extras --dev
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest --cov=permdiff --cov-fail-under=80
uv run pytest -m slow
scripts/quickstart_check.sh
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| pydantic v2 parsing 100K records exceeds 20 s | Low | `model_validate_json` per line is fast; if needed, `TypeAdapter` + `orjson` behind an optional extra |
| Frozen models with `Mapping[str, Any]` still expose mutable dicts | Medium | validators convert to `MappingProxyType`-like immutable via `types.MappingProxyType` is not JSON-serializable; instead deep-copy on access in `Redactor` and document; property test that redaction never mutates input |
| `git archive` unavailable for a path that does not exist at base ref | Medium | detect and report "policy path missing at <ref>" as `PolicyError`; treat as all-`error/unsupported` only if user passes `--allow-missing-base` (later) |
| Windows path and permission semantics for 0700 temp dirs | Low | `tempfile.mkdtemp` defaults; skip permission assert on Windows |
| Entry-point discovery slows CLI start | Low | lazy discovery only when spec is not built in |
| Demo corpus accidentally looks like real data | Low | generated from word lists; reviewed; sentinel test |

## Acceptance

- [x] All ten stories done and marked in `03-epics.md`
- [ ] Validation commands green on CI (local run green; CI not yet observed)
- [x] `pip install .` in a clean venv, then `permdiff demo` prints a report with exit 2
- [x] `permdiff diff` on a real repo with a Python policy works end to end
