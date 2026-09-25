"""Shared fixtures. Story-specific fixtures are added as stories land."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from permdiff.errors import EngineError
from permdiff.models import ToolCall
from tests.redaction_harness import sentinel_calls

OPA_FIXTURES = Path(__file__).parent / "fixtures" / "opa"

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


@pytest.fixture(scope="session")
def opa_bin() -> Path:
    """The pinned opa binary (downloaded once into the user cache); skips when offline."""
    from permdiff.evaluators.opa.binary import resolve_binary  # noqa: PLC0415

    try:
        return resolve_binary()
    except EngineError as exc:
        pytest.skip(f"opa binary unavailable: {exc}")


BASE_REGO = """package agent.authz

import rego.v1

default decision := {"effect": "deny", "rule": "default"}

decision := {"effect": "allow", "rule": "read"} if input.tool.name == "github.read"

decision := {"effect": "allow", "rule": "refund"} if input.tool.name == "stripe.refund"
"""

HEAD_REGO = """package agent.authz

import rego.v1

default decision := {"effect": "deny", "rule": "default"}

decision := {"effect": "allow", "rule": "read"} if input.tool.name == "github.read"

decision := {"effect": "require_approval", "reason": "amount>500", "rule": "refund-large"} if {
    input.tool.name == "stripe.refund"
    input.arguments.amount > 500
}

decision := {"effect": "allow", "rule": "refund-small"} if {
    input.tool.name == "stripe.refund"
    input.arguments.amount <= 500
}

decision := {"effect": "allow", "rule": "delete"} if input.tool.name == "github.delete_branch"
"""


@pytest.fixture
def rego_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "policy").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    (repo / "policy" / "agent.rego").write_text(BASE_REGO, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "tag", "v-base")
    (repo / "policy" / "agent.rego").write_text(HEAD_REGO, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "head")
    return repo


@pytest.fixture
def traces(tmp_path: Path) -> Path:
    def rec(i: int, tool: str, amount: int | None = None) -> str:
        return json.dumps(
            {
                "id": f"c{i}",
                "timestamp": f"2026-09-2{i}T12:00:00Z",
                "principal": {"id": f"user{i}"},
                "agent": {"id": "bot"},
                "tool": {"name": tool},
                "arguments": {"amount": amount} if amount is not None else None,
            }
        )

    path = tmp_path / "t.jsonl"
    lines = [
        rec(1, "github.read"),
        rec(2, "stripe.refund", 900),
        rec(3, "stripe.refund", 100),
        rec(4, "github.delete_branch"),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
