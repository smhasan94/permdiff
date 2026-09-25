"""AC-L3.10: the README quickstart for Claude Code sessions produces a real report."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from permdiff.cli.main import cli
from tests.conftest import git

ROOT = Path(__file__).parents[2]
EXAMPLES = ROOT / "examples" / "claude-code"
FIXTURE = ROOT / "tests" / "fixtures" / "claude_code" / "session.jsonl"
ENGINE = "python:permdiff.demo.engine:evaluate"


@pytest.fixture
def policy_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    for tag, version in (("v-base", "policy_base"), ("v-head", "policy_head")):
        shutil.rmtree(repo / "policy", ignore_errors=True)
        shutil.copytree(EXAMPLES / version, repo / "policy")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", version)
        git(repo, "tag", tag)
    return repo


def test_example_policies_report_the_expected_transitions(
    policy_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("USER", "dev-user")
    result = CliRunner().invoke(
        cli,
        [
            "diff",
            "--repo",
            str(policy_repo),
            "--base",
            "v-base",
            "--head",
            "v-head",
            "--policy",
            "policy",
            "--engine",
            ENGINE,
            "--from",
            "claude-code",
            "--traces",
            str(FIXTURE),
            "--principal-from",
            "env:USER",
            "--format",
            "json",
            "--salt",
            "00",
            "--include-decisions",
        ],
    )

    assert result.exit_code == 2, result.output
    doc = json.loads(result.stdout)
    by_tool = {(g["cls"], g["label"]): g["effects"] for g in doc["groups"]}
    assert by_tool[("widening", "WebFetch")] == "deny → allow"
    assert by_tool[("tightening", "Write")] == "allow → deny"
    assert by_tool[("tightening", "Bash")] == "allow → require_approval"
    assert doc["counts"]["by_class"] == {"widening": 1, "tightening": 2, "unchanged": 4}
    # Claude Code denied two calls the base policy allows and ran an MCP call it denies.
    assert doc["counts"]["recorded_disagreements"] == 3
    assert len(doc["decisions"]) == 7
    assert "dev-user" not in result.stdout  # principals are hashed outside the terminal format
    assert "/etc/hosts" not in result.stdout  # argument values are redacted by default
