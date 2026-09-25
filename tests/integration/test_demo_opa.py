"""Demo on OPA matches the Python rule tables call for call (NFR-Q3 golden)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from permdiff import api, demo
from permdiff.cli import demo as demo_module
from permdiff.cli.main import cli
from permdiff.errors import EngineError
from permdiff.models import TransitionClass
from permdiff.policy import DirectorySource

GOLDEN = Path(__file__).parents[1] / "golden" / "opa_demo_transitions.json"


def _classes(engine: str, options: dict[str, object]) -> dict[str, str]:
    imported = api.load_traces([demo.CORPUS], fmt="jsonl")
    report = api.diff_sources(
        traces=imported.calls,
        base=DirectorySource(demo.POLICY_BASE, demo.BASE_LABEL),
        head=DirectorySource(demo.POLICY_HEAD, demo.HEAD_LABEL),
        policy_path="demo/policy",
        engine=engine,
        engine_options=options,
        salt=bytes(16),
    )
    return {t.call.id: t.cls.value for t in report.transitions}


def test_opa_demo_matches_golden_and_python_engine(opa_bin: Path) -> None:
    opa = _classes("opa", {"decision": demo.OPA_DECISION, "opa_bin": opa_bin})
    python = _classes(demo.ENGINE_SPEC, {})

    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(json.dumps(opa, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    assert opa == golden, "rerun with UPDATE_GOLDEN=1 to accept"
    assert opa == python
    counts = {cls: sum(1 for v in opa.values() if v == cls) for cls in TransitionClass}
    assert counts[TransitionClass.WIDENING] == 6
    assert counts[TransitionClass.TIGHTENING] == 37
    assert counts[TransitionClass.CANT_EVALUATE] == 5
    assert counts[TransitionClass.ATTRIBUTION_CHANGE] == 0


def test_demo_auto_uses_opa_when_installed(opa_bin: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERMDIFF_OPA_BIN", str(opa_bin))

    result = CliRunner().invoke(cli, ["demo", "--no-color", "--quiet"])

    assert result.exit_code == 2, result.output
    assert "engine opa data.agent.authz.decision" in result.stdout
    assert "newly ALLOWED               6   github.delete_branch   ⚠ widening" in result.stdout
    assert (
        "can't evaluate              5   missing context: principal.attrs.department"
        in result.stdout
    )
    assert "note:" not in result.stderr


def test_demo_auto_falls_back_to_python_with_a_note(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unavailable(*args: object, **kwargs: object) -> Path:
        raise EngineError("not installed")

    monkeypatch.setattr("permdiff.evaluators.opa.binary.resolve_binary", _unavailable)

    result = CliRunner().invoke(cli, ["demo", "--no-color", "--quiet"])

    assert result.exit_code == 2, result.output
    assert "engine python:permdiff.demo.engine:evaluate" in result.stdout
    assert demo_module.FALLBACK_NOTE in result.stderr


def test_demo_engine_opa_explicit_propagates_unavailability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _unavailable(*args: object, **kwargs: object) -> Path:
        raise EngineError("download failed: offline")

    monkeypatch.setattr("permdiff.evaluators.opa.binary.resolve_binary", _unavailable)

    result = CliRunner().invoke(cli, ["demo", "--engine", "opa"])

    assert result.exit_code == 1
    assert "error: download failed: offline" in result.stderr
