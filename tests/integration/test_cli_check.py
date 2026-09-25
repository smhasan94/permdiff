from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from permdiff.cli.main import cli
from tests.conftest import GitRepo

PY_ENGINE = "python:tests.fixtures.py_engine.rules:by_table"


def _check(repo: Path, traces_path: Path, *extra: str) -> tuple[int, str, str]:
    result = CliRunner().invoke(
        cli,
        ["check", "--repo", str(repo), "--base", "v-base", "--traces", str(traces_path), *extra],
    )
    return result.exit_code, result.stdout, result.stderr


def test_check_reports_counts_and_both_refs_ok(
    rego_repo: Path, traces: Path, opa_bin: Path
) -> None:
    code, out, _ = _check(rego_repo, traces, "--engine", "opa", "--opa-bin", str(opa_bin))

    assert code == 0, out
    assert "traces: 4 calls (0 skipped, 0 filtered out)" in out
    assert "v-base (" in out
    assert out.count(": ok") == 2


def test_check_fails_when_head_does_not_compile(
    rego_repo: Path, traces: Path, opa_bin: Path
) -> None:
    (rego_repo / "policy" / "agent.rego").write_text("package x\n\nbroken (\n", encoding="utf-8")

    code, out, _ = _check(
        rego_repo, traces, "--head", "WORKTREE", "--engine", "opa", "--opa-bin", str(opa_bin)
    )

    assert code == 1
    assert "v-base (" in out
    assert "WORKTREE: FAIL" in out


def test_check_with_python_engine_and_bad_ref(git_repo: GitRepo, traces: Path) -> None:
    code, out, _ = _check(git_repo.path, traces, "--engine", PY_ENGINE)
    assert code == 0
    assert out.count(": ok") == 2

    code, _, err = _check(git_repo.path, traces, "--engine", PY_ENGINE, "--head", "nope")
    assert code == 1
    assert "nope" in err
