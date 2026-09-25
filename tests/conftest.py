"""Shared fixtures. Story-specific fixtures are added as stories land."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from permdiff.models import ToolCall
from tests.redaction_harness import sentinel_calls

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_AUTHOR_DATE": "2026-09-20T00:00:00Z",
    "GIT_COMMITTER_DATE": "2026-09-20T00:00:00Z",
}


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` with a hermetic config; return stdout stripped."""
    env = {**os.environ, **GIT_ENV}
    argv = ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args]
    completed = subprocess.run(  # noqa: S603
        argv,
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


@dataclass(frozen=True)
class GitRepo:
    """A temp repo whose ``policy/rules.json`` differs between two commits."""

    path: Path
    policy_path: str
    base_sha: str
    head_sha: str
    base_rules: dict[str, str]
    head_rules: dict[str, str]


@pytest.fixture
def git_repo(tmp_path: Path) -> GitRepo:
    repo = tmp_path / "repo"
    policy = repo / "policy"
    policy.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")

    base_rules = {"stripe.refund": "deny", "github.read": "allow"}
    (policy / "rules.json").write_text(json.dumps(base_rules), encoding="utf-8")
    (repo / "README.md").write_text("not policy\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base policy")
    base_sha = git(repo, "rev-parse", "HEAD")
    git(repo, "tag", "v-base")

    head_rules = {"stripe.refund": "require_approval", "github.read": "allow", "x": "allow"}
    (policy / "rules.json").write_text(json.dumps(head_rules), encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "head policy")
    head_sha = git(repo, "rev-parse", "HEAD")

    return GitRepo(
        path=repo,
        policy_path="policy",
        base_sha=base_sha,
        head_sha=head_sha,
        base_rules=base_rules,
        head_rules=head_rules,
    )


@pytest.fixture
def sentinel_corpus() -> tuple[ToolCall, ...]:
    """Calls seeded with unique PII-like strings; see ``tests/redaction_harness.py``."""
    return sentinel_calls()
