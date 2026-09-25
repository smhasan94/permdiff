from __future__ import annotations

import json
import os
from pathlib import Path

import jsonschema

from permdiff import schemas
from permdiff.redact import Redactor
from permdiff.report.exit_codes import FailOn, gate
from permdiff.report.json_ import render_json
from permdiff.report.view import build_view
from tests.redaction_harness import SENTINELS, assert_no_sentinels
from tests.report_fixtures import FIXED_SALT, sample_report

GOLDEN = Path(__file__).parents[2] / "golden" / "json_report.json"


def _render(include_decisions: bool = False, **view_kwargs: object) -> str:
    view = build_view(
        sample_report(),
        redactor=Redactor(salt=FIXED_SALT),
        include_decisions=include_decisions,
        **view_kwargs,  # type: ignore[arg-type]
    )
    return render_json(
        view,
        exit_code=gate(view, FailOn.WIDEN),
        fail_on=FailOn.WIDEN,
        include_decisions=include_decisions,
    )


def test_matches_golden() -> None:
    out = _render()
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(out, encoding="utf-8")

    assert out == GOLDEN.read_text(encoding="utf-8"), "rerun with UPDATE_GOLDEN=1 to accept"


def test_envelope_is_versioned_and_validates_against_shipped_schema() -> None:
    doc = json.loads(_render(include_decisions=True))

    jsonschema.Draft202012Validator(schemas.json_schema("report")).validate(doc)
    assert list(doc)[:4] == ["permdiff_report", "header", "window", "exit_code"]
    assert doc["permdiff_report"] == "1"
    assert doc["exit_code"] == 2
    assert doc["fail_on"] == "widen"
    assert doc["gate_reason"] == "widening found; --fail-on widen"
    assert doc["counts"]["by_class"]["widening"] == 3
    assert doc["group_by"] == ["tool"]
    assert doc["groups"][0]["key"] == {"tool": "github.delete_branch"}
    assert doc["groups"][0]["samples"][0]["call"]["principal"]["id"].startswith("principal:")


def test_decisions_are_opt_in() -> None:
    without = json.loads(_render())
    with_decisions = json.loads(_render(include_decisions=True))

    assert without["decisions"] is None
    assert len(with_decisions["decisions"]) == 14
    assert {"call", "base", "head", "cls"} <= set(with_decisions["decisions"][0])


def test_safe_output_leaks_no_sentinels_even_with_decisions() -> None:
    out = _render(include_decisions=True)

    assert_no_sentinels(out)
    assert SENTINELS["principal_id"] not in out


def test_report_schema_is_checked_in() -> None:
    on_disk = json.loads(
        (Path(schemas.__file__).parent / "report.json").read_text(encoding="utf-8")
    )

    assert on_disk == schemas.json_schema("report")
