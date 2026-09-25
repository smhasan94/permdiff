from __future__ import annotations

import json
import os
from pathlib import Path

import jsonschema

from permdiff.models import Decision, Effect
from permdiff.redact import Redactor
from permdiff.report.exit_codes import EXIT_GATE, FailOn, gate
from permdiff.report.sarif import render_sarif
from permdiff.report.view import build_view
from tests.redaction_harness import SENTINELS, assert_no_sentinels
from tests.report_fixtures import FIXED_SALT, sample_report

GOLDEN = Path(__file__).parents[2] / "golden" / "sarif_report.sarif"
SCHEMA = json.loads(
    (Path(__file__).parents[2] / "vendor" / "sarif-schema-2.1.0.json").read_text(encoding="utf-8")
)


def _render(**view_kwargs: object) -> str:
    view = build_view(sample_report(), redactor=Redactor(salt=FIXED_SALT), **view_kwargs)  # type: ignore[arg-type]
    return render_sarif(view, exit_code=gate(view, FailOn.WIDEN), fail_on=FailOn.WIDEN)


def test_matches_golden() -> None:
    out = _render()
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(out, encoding="utf-8")

    assert out == GOLDEN.read_text(encoding="utf-8"), "rerun with UPDATE_GOLDEN=1 to accept"


def test_validates_against_vendored_sarif_schema() -> None:
    doc = json.loads(_render())

    jsonschema.Draft7Validator(SCHEMA).validate(doc)
    assert doc["version"] == "2.1.0"


def test_one_result_per_group_with_levels_counts_and_rules() -> None:
    doc = json.loads(_render())
    run = doc["runs"][0]

    assert [r["id"] for r in run["tool"]["driver"]["rules"]][:3] == [
        "permdiff/widening",
        "permdiff/tightening",
        "permdiff/cant-evaluate",
    ]
    assert [(r["ruleId"], r["level"], r["properties"]["count"]) for r in run["results"]] == [
        ("permdiff/widening", "error", 2),
        ("permdiff/widening", "error", 1),
        ("permdiff/tightening", "warning", 3),
        ("permdiff/tightening", "warning", 1),
        ("permdiff/cant-evaluate", "warning", 2),
    ]
    assert "2 calls" in run["results"][0]["message"]["text"]
    assert run["results"][0]["properties"]["security-severity"] == "8.0"


def test_every_result_has_physical_and_logical_locations() -> None:
    doc = json.loads(_render())

    for result in doc["runs"][0]["results"]:
        (location,) = result["locations"]
        physical = location["physicalLocation"]
        assert (
            physical["artifactLocation"]["uri"] == "policy/agent.rego"
        )  # first policy file fallback
        assert physical["region"]["startLine"] >= 1
        kinds = {loc["kind"]: loc["name"] for loc in location["logicalLocations"]}
        assert "function" in kinds
        assert kinds["member"].startswith("principal:")


def test_file_line_attribution_becomes_the_physical_location() -> None:
    base = sample_report()
    t = base.transitions[0]
    head = Decision(
        call_id=t.call.id, effect=Effect.ALLOW, determining=("agent.rego:42",), engine="opa"
    )
    report = base.model_copy(
        update={"transitions": (t.model_copy(update={"head": head}), *base.transitions[1:])}
    )
    view = build_view(report, redactor=Redactor(salt=FIXED_SALT))

    doc = json.loads(render_sarif(view, exit_code=EXIT_GATE, fail_on=FailOn.WIDEN))

    physical = doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
    assert physical == {
        "artifactLocation": {"uri": "policy/agent.rego"},
        "region": {"startLine": 42},
    }


def test_fingerprints_are_stable_per_group_across_runs_and_salts() -> None:
    a = json.loads(_render())
    b = json.loads(
        render_sarif(
            build_view(sample_report(), redactor=Redactor(salt=bytes(16))),
            exit_code=EXIT_GATE,
            fail_on=FailOn.WIDEN,
        )
    )

    fa = [r["partialFingerprints"]["primaryLocationLineHash"] for r in a["runs"][0]["results"]]
    fb = [r["partialFingerprints"]["primaryLocationLineHash"] for r in b["runs"][0]["results"]]
    assert fa == fb
    assert len(set(fa)) == len(fa)


def test_no_policy_files_falls_back_to_the_policy_dir() -> None:
    base = sample_report()
    report = base.model_copy(update={"header": base.header.model_copy(update={"policy_files": ()})})
    view = build_view(report, redactor=Redactor(salt=FIXED_SALT))

    doc = json.loads(render_sarif(view, exit_code=EXIT_GATE, fail_on=FailOn.WIDEN))

    assert (
        doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        == "policy"
    )


def test_safe_output_leaks_no_sentinels() -> None:
    out = _render()

    assert_no_sentinels(out)
    assert SENTINELS["principal_id"] not in out
