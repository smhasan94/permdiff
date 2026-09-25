from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from permdiff.cli import diff as diff_module
from permdiff.cli.main import cli
from tests.conftest import GitRepo

ENGINE = "python:tests.fixtures.py_engine.rules:by_table"
Run = Callable[..., Result]


def _record(i: int, tool: str, args: dict[str, object] | None = None) -> str:
    return json.dumps(
        {
            "id": f"c{i}",
            "timestamp": f"2026-09-2{i}T12:00:00Z",
            "principal": {"id": f"user{i}@example.com"},
            "agent": {"id": "bot"},
            "tool": {"name": tool},
            "arguments": args or {"secret": "hunter2", "n": i},
        }
    )


@pytest.fixture
def traces(tmp_path: Path) -> Path:
    path = tmp_path / "t.jsonl"
    lines = [_record(1, "stripe.refund"), _record(2, "github.read"), _record(3, "x"), "{bad"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def run(git_repo: GitRepo, traces: Path) -> Run:
    def _run(*extra: str, before: tuple[str, ...] = ()) -> Result:
        args = [
            *before,
            "diff",
            "--repo",
            str(git_repo.path),
            "--base",
            "v-base",
            "--head",
            "HEAD",
            "--engine",
            ENGINE,
            "--traces",
            str(traces),
            "--no-color",
            *extra,
        ]
        return CliRunner().invoke(cli, args)

    return _run


def test_widening_exits_two_and_prints_report(run: Run) -> None:
    result = run()

    assert result.exit_code == 2, result.output
    assert "permdiff: v-base → HEAD   (3 calls" in result.stdout
    assert "now REQUIRE_APPROVAL        1   stripe.refund   ⚠ widening" in result.stdout
    assert "newly ALLOWED               1   x   ⚠ widening" in result.stdout
    assert "skipped 1 malformed" in result.stdout
    assert "exit 2 (widening found; --fail-on widen)" in result.stdout


def test_safe_redaction_hides_argument_values_but_shows_principal(run: Run) -> None:
    result = run()

    assert "hunter2" not in result.stdout
    assert '"secret": "<str:7>"' in result.stdout
    assert "user1@example.com" in result.stdout


def test_redact_none_and_show_args_reveal_values(run: Run) -> None:
    assert '"secret": "hunter2"' in run("--redact", "none").stdout
    shown = run("--show-args", "secret").stdout
    assert '"secret": "hunter2"' in shown
    assert '"n": "<int>"' in shown


def test_fail_on_none_exits_zero(run: Run) -> None:
    result = run("--fail-on", "none")

    assert result.exit_code == 0
    assert "exit 0 (nothing matched --fail-on none)" in result.stdout


def test_allow_widening_exits_zero_and_records_actor(
    run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_ACTOR", "octocat")

    result = run("--allow-widening", "ticket-7")

    assert result.exit_code == 0
    assert "allow-widening by octocat: ticket-7" in result.stdout


def test_quiet_prints_only_the_summary(run: Run) -> None:
    result = run("--quiet")

    assert "c1" not in result.stdout
    assert "now REQUIRE_APPROVAL" in result.stdout


def test_fixed_salt_makes_output_reproducible(run: Run) -> None:
    a = run("--salt", "00ff").stdout
    b = run("--salt", "00ff").stdout

    assert a == b


def test_bad_salt_is_a_config_error(run: Run) -> None:
    result = run("--salt", "zz")

    assert result.exit_code == 1
    assert "--salt" in result.stderr


def test_worktree_head_sees_uncommitted_policy(run: Run, git_repo: GitRepo) -> None:
    (git_repo.path / "policy" / "rules.json").write_text(
        json.dumps({"stripe.refund": "allow", "github.read": "allow", "x": "deny"}),
        encoding="utf-8",
    )

    result = run("--head", "WORKTREE")

    assert "v-base → WORKTREE" in result.stdout
    assert "newly ALLOWED               1   stripe.refund   ⚠ widening" in result.stdout
    assert "head WORKTREE" in result.stdout


def test_bad_ref_exits_one_and_names_the_flag(run: Run) -> None:
    result = run("--base", "no-such-ref")

    assert result.exit_code == 1
    assert "error: cannot resolve ref 'no-such-ref' for --base/--head" in result.stderr
    assert result.stdout == ""


def test_bad_engine_exits_one_and_names_the_flag(run: Run) -> None:
    result = run("--engine", "python:no_such_module_xyz:fn")

    assert result.exit_code == 1
    assert "--engine python:no_such_module_xyz:fn" in result.stderr


def test_missing_traces_exits_one_and_names_the_flag(run: Run, tmp_path: Path) -> None:
    result = run("--traces", str(tmp_path / "missing-*.jsonl"))

    assert result.exit_code == 1
    assert "--traces" in result.stderr


def test_strict_aborts_on_malformed_line(run: Run, traces: Path) -> None:
    result = run("--strict")

    assert result.exit_code == 1
    assert f"{traces}:4" in result.stderr


def test_unknown_from_lists_importers(run: Run) -> None:
    result = run("--from", "nope")

    assert result.exit_code == 1
    assert "jsonl" in result.stderr


def test_verbose_logs_timings(run: Run, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="permdiff"):
        result = run(before=("--verbose",))

    assert result.exit_code == 2
    messages = [r.getMessage() for r in caplog.records]
    assert any(re.match(r"imported 3 calls \(1 skipped\) in \d+\.\d+s", m) for m in messages)
    assert any(m.startswith("evaluated 3 calls at both refs in") for m in messages)


def test_debug_keeps_policy_temp_dirs(run: Run, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="permdiff"):
        result = run(before=("--debug",))

    assert result.exit_code == 2
    kept = [r.getMessage() for r in caplog.records if "keeping policy temp dir" in r.getMessage()]
    assert len(kept) == 2
    for message in kept:
        path = Path(message.rsplit(" ", 1)[1])
        assert (path / "policy" / "rules.json").exists()


def test_unsupported_format_is_rejected(run: Run) -> None:
    result = run("--format", "json")

    assert result.exit_code == 2
    assert "terminal" in result.stderr


def test_empty_salt_is_a_config_error(run: Run) -> None:
    result = run("--salt", "")

    assert result.exit_code == 1
    assert "--salt must not be empty" in result.stderr


def test_actor_falls_back_to_git_then_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_ACTOR", raising=False)
    assert isinstance(diff_module.actor(), str)

    def _raise(*args: object, **kwargs: object) -> None:
        raise OSError("no git")

    monkeypatch.setattr("subprocess.run", _raise)
    assert diff_module.actor() == "unknown"
