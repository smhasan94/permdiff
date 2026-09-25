"""Demo on Cedar matches the OPA golden and the Python engine call for call (NFR-Q3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from permdiff import api, demo
from permdiff.cli.main import cli
from permdiff.policy import DirectorySource

pytest.importorskip("cedarpy")

GOLDEN = Path(__file__).parents[1] / "golden" / "opa_demo_transitions.json"


def test_cedar_demo_matches_the_opa_golden() -> None:
    imported = api.load_traces([demo.CORPUS], fmt="jsonl")
    report = api.diff_sources(
        traces=imported.calls,
        base=DirectorySource(demo.POLICY_BASE, demo.BASE_LABEL),
        head=DirectorySource(demo.POLICY_HEAD, demo.HEAD_LABEL),
        policy_path="demo/policy",
        engine="cedar",
        engine_options={"resource": demo.CEDAR_RESOURCE},
        salt=bytes(16),
    )

    classes = {t.call.id: t.cls.value for t in report.transitions}
    assert classes == json.loads(GOLDEN.read_text(encoding="utf-8"))
    errors = [t for t in report.transitions if t.cls.value == "cant_evaluate"]
    assert all(
        t.head.error_kind is not None and t.head.error_kind.value == "missing_context"
        for t in errors
    )
    assert all(t.head.reasons == ("department",) for t in errors)


def test_demo_engine_cedar_runs_and_reports_approval() -> None:
    result = CliRunner().invoke(cli, ["demo", "--engine", "cedar", "--no-color", "--quiet"])

    assert result.exit_code == 2, result.output
    assert 'engine cedar Action::"{tool.name}"' in result.stdout
    assert "now REQUIRE_APPROVAL       22   stripe.refund" in result.stdout
    assert "can't evaluate              5   missing context: department" in result.stdout
