"""Rego shim and cases document for batch evaluation (AC-10.2, AC-10.5)."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from permdiff.models import Frozen, ToolCall

SHIM_PACKAGE = "permdiff"
CASES_ROOT = "permdiff_cases"
ND_ROOT = "permdiff_nd"
RESULTS_RULE = "results"
ND_MISS_PREFIX = "permdiff-nd-miss:"
SHIM_FILE = "permdiff_shim.rego"
CASES_FILE = "permdiff_cases.json"

_DECISION_PATH = re.compile(r"^data(\.[A-Za-z_][A-Za-z0-9_]*)+$")
_NS_PER_S = 1_000_000_000


class NdOverride(Frozen):
    """One builtin replaced by a lookup into ``data.permdiff_nd[builtin]`` keyed by args."""

    builtin: str

    @property
    def mock_name(self) -> str:
        return "permdiff_mock_" + self.builtin.replace(".", "_")


def validate_decision_path(path: str) -> str:
    if not _DECISION_PATH.match(path):
        msg = f"--decision must look like data.pkg.rule, got {path!r}"
        raise ValueError(msg)
    return path


def timestamp_ns(call: ToolCall) -> int:
    ts = call.timestamp
    return int(ts.timestamp()) * _NS_PER_S + ts.microsecond * 1000


def render_shim(decision_path: str, *, nd_overrides: Sequence[NdOverride] = ()) -> str:
    """Rego that evaluates ``decision_path`` once per case with input and clock injected."""
    validate_decision_path(decision_path)
    withs = " ".join(f"with {o.builtin} as {o.mock_name}" for o in nd_overrides)
    lines = [f"package {SHIM_PACKAGE}", "", "import rego.v1", ""]
    for o in nd_overrides:
        lines += [
            f"{o.mock_name}(args) := resp if {{",
            f'    resp := data.{ND_ROOT}["{o.builtin}"][json.marshal(args)]',
            "}",
            "",
            f"{o.mock_name}(args) := resp if {{",
            f'    not data.{ND_ROOT}["{o.builtin}"][json.marshal(args)]',
            f'    key := concat("", ["{ND_MISS_PREFIX}{o.builtin}:", json.marshal(args)])',
            "    resp := to_number(key)",
            "}",
            "",
        ]
    lines += [
        f"{RESULTS_RULE} contains r if {{",
        f"    some c in data.{CASES_ROOT}",
        f"    v := {decision_path} with input as c.call with time.now_ns as c.ts_ns {withs}".rstrip(
            " "
        ),
        '    r := {"id": c.id, "value": v}',
        "}",
        "",
    ]
    return "\n".join(lines)


def render_cases(calls: Sequence[ToolCall]) -> bytes:
    """``{"permdiff_cases": [{"id", "ts_ns", "call"}, ...]}`` as compact UTF-8 JSON."""
    cases = [
        {"id": c.id, "ts_ns": timestamp_ns(c), "call": c.model_dump(mode="json")} for c in calls
    ]
    return json.dumps({CASES_ROOT: cases}, separators=(",", ":")).encode("utf-8")
