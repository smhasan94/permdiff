from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from permdiff.errors import PolicyError
from permdiff.policy.source import GitRefSource, MaterializedPolicy, WorktreeSource, source_for
from tests.conftest import GitRepo


def _rules(m: MaterializedPolicy) -> dict[str, str]:
    data: dict[str, str] = json.loads((m.path / "rules.json").read_text(encoding="utf-8"))
    return data


def test_git_ref_source_materializes_each_ref(git_repo: GitRepo) -> None:
    base = GitRefSource(git_repo.path, "v-base", "policy")
    head = GitRefSource(git_repo.path, "HEAD", "policy")

    with base.materialize() as b, head.materialize() as h:
        assert _rules(b) == git_repo.base_rules
        assert _rules(h) == git_repo.head_rules
        assert b.sha == git_repo.base_sha
        assert h.sha == git_repo.head_sha
        assert b.label == "v-base"
        assert h.label == "HEAD"
        assert not b.is_worktree
        assert b.path != h.path


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_temp_dir_is_private_and_removed_on_exit(git_repo: GitRepo) -> None:
    src = GitRefSource(git_repo.path, "HEAD", "policy")

    with src.materialize() as m:
        root = m.path.parent
        mode = stat.S_IMODE(root.stat().st_mode)
        assert mode == 0o700
        assert m.path.is_dir()

    assert not root.exists()


def test_temp_dir_is_removed_when_the_body_raises(git_repo: GitRepo) -> None:
    src = GitRefSource(git_repo.path, "HEAD", "policy")
    root: Path | None = None

    with pytest.raises(RuntimeError), src.materialize() as m:
        root = m.path.parent
        raise RuntimeError("boom")

    assert root is not None
    assert not root.exists()


def test_keep_leaves_temp_dir_in_place(git_repo: GitRepo) -> None:
    src = GitRefSource(git_repo.path, "HEAD", "policy")

    with src.materialize(keep=True) as m:
        root = m.path.parent

    assert root.exists()


def test_invalid_ref_fails_before_any_temp_dir(git_repo: GitRepo) -> None:
    src = GitRefSource(git_repo.path, "does-not-exist", "policy")

    with pytest.raises(PolicyError, match="does-not-exist"), src.materialize():
        pass


def test_missing_policy_path_at_ref_is_reported(git_repo: GitRepo) -> None:
    src = GitRefSource(git_repo.path, "HEAD", "elsewhere")

    with pytest.raises(PolicyError, match="elsewhere"), src.materialize():
        pass


def test_worktree_source_sees_uncommitted_changes(git_repo: GitRepo) -> None:
    live = {"stripe.refund": "allow"}
    (git_repo.path / "policy" / "rules.json").write_text(json.dumps(live), encoding="utf-8")
    src = WorktreeSource(git_repo.path, "policy")

    with src.materialize() as m:
        assert _rules(m) == live
        assert m.is_worktree
        assert m.sha is None
        assert m.label == "WORKTREE"
        assert git_repo.path not in m.path.parents


def test_worktree_source_missing_path_is_a_policy_error(git_repo: GitRepo) -> None:
    src = WorktreeSource(git_repo.path, "nope")

    with pytest.raises(PolicyError, match="nope"), src.materialize():
        pass


def test_sources_work_from_a_subdirectory(git_repo: GitRepo) -> None:
    sub = git_repo.path / "policy"

    with GitRefSource(sub, "v-base", "policy").materialize() as m:
        assert _rules(m) == git_repo.base_rules
    with WorktreeSource(sub, "policy").materialize() as w:
        assert _rules(w) == git_repo.head_rules


def test_source_for_dispatches_on_worktree_keyword(git_repo: GitRepo) -> None:
    assert isinstance(source_for(git_repo.path, "WORKTREE", "policy"), WorktreeSource)
    assert isinstance(source_for(git_repo.path, "HEAD", "policy"), GitRefSource)
    assert source_for(git_repo.path, "HEAD", "policy").label == "HEAD"


def test_worktree_source_copies_a_single_policy_file(git_repo: GitRepo) -> None:
    src = WorktreeSource(git_repo.path, "policy/rules.json")

    with src.materialize() as m:
        assert m.path.is_file()
        assert json.loads(m.path.read_text(encoding="utf-8")) == git_repo.head_rules
