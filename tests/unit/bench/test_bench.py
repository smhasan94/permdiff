from __future__ import annotations

import json
from pathlib import Path

from bench import gate, generate, run

from permdiff.importers.jsonl import JsonlImporter


def test_generator_is_deterministic_and_valid(tmp_path: Path) -> None:
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    generate.write(a, 300)
    generate.write(b, 300)

    assert a.read_bytes() == b.read_bytes()
    result = JsonlImporter().read(a, strict=True)
    assert result.stats.read == 300
    assert "@" not in a.read_text(encoding="utf-8")


def test_runner_produces_the_json_shape_with_the_python_engine() -> None:
    result = run.run("python", 400)

    assert result["engine"] == "python"
    assert result["n"] == 400
    assert set(result["phases"]) == {"import", "diff", "report", "total"}
    assert result["peak_rss_mb"] > 0
    assert result["counts"]["evaluated"] == 400


def test_gate_flags_regressions_and_missing_targets() -> None:
    baseline = {"phases": {"import": 1.0, "diff": 2.0, "report": 0.5, "total": 3.5}}
    ok = {
        "engine": "python",
        "phases": {"import": 1.2, "diff": 2.5, "report": 0.5, "total": 4.2},
        "peak_rss_mb": 300,
    }
    slow = {
        "engine": "python",
        "phases": {"import": 1.0, "diff": 4.0, "report": 0.5, "total": 5.5},
        "peak_rss_mb": 300,
    }
    huge = {
        "engine": "python",
        "phases": {"import": 1.0, "diff": 2.0, "report": 0.5, "total": 61},
        "peak_rss_mb": 2048,
    }

    assert gate.regressions(ok, baseline) == []
    assert gate.regressions(slow, baseline)[0] == "diff: 4.00s > 1.5x baseline 2.00s"
    problems = gate.regressions(huge, baseline)
    assert any("60s target" in p for p in problems)
    assert any("1024 MB" in p for p in problems)


def test_gate_cli_passes_without_a_baseline_and_fails_on_regression(tmp_path: Path) -> None:
    result = tmp_path / "r.json"
    result.write_text(
        json.dumps({"engine": "opa", "phases": {"diff": 9.0, "total": 9.0}, "peak_rss_mb": 1}),
        encoding="utf-8",
    )
    baselines = tmp_path / "b.json"
    baselines.write_text(
        json.dumps({"ci-linux": {"opa": {"phases": {"diff": 2.0}}}}), encoding="utf-8"
    )

    assert (
        gate.main(["--result", str(result), "--baseline", str(baselines), "--platform", "laptop"])
        == 0
    )
    assert (
        gate.main(["--result", str(result), "--baseline", str(baselines), "--platform", "ci-linux"])
        == 1
    )
