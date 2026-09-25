from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from permdiff.cli.main import cli
from tests.conftest import GitRepo

ENGINE = "python:tests.fixtures.py_engine.rules:by_table"


def _traces(tmp_path: Path) -> Path:
    path = tmp_path / "t.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "c1",
                "timestamp": "2026-09-20T12:00:00Z",
                "principal": {"id": "u"},
                "agent": {"id": "a"},
                "tool": {"name": "stripe.refund"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_diff_runs_from_config_alone(
    git_repo: GitRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    traces = _traces(tmp_path)
    (git_repo.path / "permdiff.toml").write_text(
        f'[policy]\nengine = "{ENGINE}"\nbase = "v-base"\n[traces]\npaths = ["{traces}"]\n'
        '[report]\nfail_on = "none"\nformat = "json"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(git_repo.path)

    result = CliRunner().invoke(cli, ["diff", "--no-color"])

    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc["header"]["base_label"] == "v-base"
    assert doc["fail_on"] == "none"


def test_env_and_flags_override_the_file(
    git_repo: GitRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    traces = _traces(tmp_path)
    (git_repo.path / "permdiff.toml").write_text(
        f'[policy]\nengine = "{ENGINE}"\nbase = "v-base"\n'
        f'[traces]\npaths = ["{traces}"]\n[report]\nfail_on = "none"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(git_repo.path)
    monkeypatch.setenv("PERMDIFF_REPORT_FAIL_ON", "widen")

    from_env = CliRunner().invoke(cli, ["diff", "--no-color", "--quiet"])
    from_flag = CliRunner().invoke(cli, ["diff", "--no-color", "--quiet", "--fail-on", "none"])

    assert from_env.exit_code == 2, from_env.output
    assert "--fail-on widen" in from_env.stdout
    assert from_flag.exit_code == 0
    assert "--fail-on none" in from_flag.stdout


def test_missing_traces_and_engine_are_named(
    git_repo: GitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo.path)

    result = CliRunner().invoke(cli, ["diff"])

    assert result.exit_code == 1
    assert "--traces" in result.stderr
    assert "permdiff.toml" in result.stderr


def test_unknown_config_key_is_reported(
    git_repo: GitRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (git_repo.path / "permdiff.toml").write_text("[report]\nsampels = 2\n", encoding="utf-8")
    monkeypatch.chdir(git_repo.path)

    result = CliRunner().invoke(
        cli, ["diff", "--traces", str(_traces(tmp_path)), "--engine", ENGINE]
    )

    assert result.exit_code == 1
    assert "unknown key report.sampels" in result.stderr


def test_explicit_config_flag(
    git_repo: GitRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    traces = _traces(tmp_path)
    cfg = tmp_path / "ci.toml"
    cfg.write_text(
        f'[policy]\nengine = "{ENGINE}"\nbase = "v-base"\n[traces]\npaths = ["{traces}"]\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(git_repo.path)

    result = CliRunner().invoke(cli, ["--config", str(cfg), "diff", "--no-color", "--quiet"])

    assert result.exit_code == 2, result.output


def test_init_writes_and_refuses_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    first = CliRunner().invoke(
        cli, ["init", "--engine", ENGINE, "--traces", "traces/*.jsonl", "--fail-on", "any-change"]
    )
    assert first.exit_code == 0, first.output
    text = (tmp_path / "permdiff.toml").read_text(encoding="utf-8")
    assert f'engine = "{ENGINE}"' in text
    assert 'paths = ["traces/*.jsonl"]' in text
    assert 'fail_on = "any-change"' in text

    second = CliRunner().invoke(cli, ["init"])
    assert second.exit_code == 1
    assert "already exists" in second.stderr

    forced = CliRunner().invoke(cli, ["init", "--force", "--base", "main"])
    assert forced.exit_code == 0
    assert 'base = "main"' in (tmp_path / "permdiff.toml").read_text(encoding="utf-8")
