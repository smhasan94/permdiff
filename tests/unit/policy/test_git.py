from __future__ import annotations

from pathlib import Path

import pytest

from permdiff import _proc
from permdiff.errors import PolicyError
from permdiff.policy import git as gitmod
from tests.conftest import GitRepo, git


def test_rev_parse_resolves_branches_tags_and_shas(git_repo: GitRepo) -> None:
    assert gitmod.rev_parse(git_repo.path, "HEAD") == git_repo.head_sha
    assert gitmod.rev_parse(git_repo.path, "main") == git_repo.head_sha
    assert gitmod.rev_parse(git_repo.path, "v-base") == git_repo.base_sha
    assert gitmod.rev_parse(git_repo.path, git_repo.base_sha[:10]) == git_repo.base_sha


def test_rev_parse_unknown_ref_reports_git_message(git_repo: GitRepo) -> None:
    with pytest.raises(PolicyError, match="nope") as exc_info:
        gitmod.rev_parse(git_repo.path, "nope")

    assert "--base/--head" in str(exc_info.value)
    assert "fetch-depth" not in str(exc_info.value)


@pytest.mark.parametrize("ref", ["--upload-pack=evil", "-x", "--output=/tmp/x", ""])
def test_option_like_refs_are_rejected_before_git_runs(
    git_repo: GitRepo, monkeypatch: pytest.MonkeyPatch, ref: str
) -> None:
    def _never(*args: object, **kwargs: object) -> None:
        raise AssertionError("git must not run")

    monkeypatch.setattr(_proc, "run", _never)

    with pytest.raises(PolicyError, match="ref"):
        gitmod.rev_parse(git_repo.path, ref)


def test_find_toplevel_from_subdirectory(git_repo: GitRepo) -> None:
    sub = git_repo.path / "policy"

    assert gitmod.find_toplevel(sub) == git_repo.path.resolve()


def test_find_toplevel_outside_a_repo_is_a_policy_error(tmp_path: Path) -> None:
    outside = tmp_path / "plain"
    outside.mkdir()

    with pytest.raises(PolicyError, match="not a git repository"):
        gitmod.find_toplevel(outside)


def test_shallow_clone_missing_ref_suggests_fetch_depth(git_repo: GitRepo, tmp_path: Path) -> None:
    clone = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth", "1", f"file://{git_repo.path}", str(clone))

    with pytest.raises(PolicyError, match="fetch-depth: 0"):
        gitmod.rev_parse(clone, git_repo.base_sha)


def test_archive_extracts_only_the_policy_path(git_repo: GitRepo, tmp_path: Path) -> None:
    dest = tmp_path / "out"
    dest.mkdir()

    gitmod.archive_to(git_repo.path, git_repo.base_sha, "policy", dest)

    assert (dest / "policy" / "rules.json").read_text(encoding="utf-8").startswith("{")
    assert not (dest / "README.md").exists()


def test_archive_missing_path_names_path_and_ref(git_repo: GitRepo, tmp_path: Path) -> None:
    with pytest.raises(PolicyError, match="missing") as exc_info:
        gitmod.archive_to(git_repo.path, git_repo.base_sha, "no-such-dir", tmp_path)

    message = str(exc_info.value)
    assert "no-such-dir" in message
    assert git_repo.base_sha[:7] in message


@pytest.mark.parametrize("bad", ["../etc", "/abs/path", "policy/../..", ""])
def test_unsafe_policy_paths_are_rejected(bad: str) -> None:
    with pytest.raises(PolicyError, match="policy path"):
        gitmod.normalize_policy_path(bad)


def test_policy_path_is_normalized() -> None:
    assert gitmod.normalize_policy_path("./policy/") == "policy"
    assert gitmod.normalize_policy_path("a/./b") == "a/b"
