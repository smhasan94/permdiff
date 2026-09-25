"""Where a policy comes from: a git ref, or the live working tree (FR-8)."""

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Protocol

from permdiff.errors import PolicyError
from permdiff.models import Frozen
from permdiff.policy import git as gitmod

log = logging.getLogger(__name__)

WORKTREE = "WORKTREE"
_TMP_PREFIX = "permdiff-policy-"


class MaterializedPolicy(Frozen):
    """A policy directory on disk for one ref, plus what the report header needs (AC-8.4)."""

    path: Path
    sha: str | None
    label: str
    is_worktree: bool


class PolicySource(Protocol):
    @property
    def label(self) -> str: ...

    def materialize(self, *, keep: bool = False) -> AbstractContextManager[MaterializedPolicy]: ...


@contextmanager
def _private_tempdir(*, keep: bool) -> Iterator[Path]:
    """0700 temp dir removed on every exit path unless ``keep`` (AC-8.2, NFR-S5)."""
    root = Path(tempfile.mkdtemp(prefix=_TMP_PREFIX))
    try:
        yield root
    finally:
        if keep:
            log.info("keeping policy temp dir %s", root)
        else:
            shutil.rmtree(root, ignore_errors=True)


class GitRefSource:
    """Policy path extracted from a committed ref with ``git archive``."""

    def __init__(self, repo: Path, ref: str, policy_path: str) -> None:
        self._repo = repo
        self._ref = ref
        self._policy_path = gitmod.normalize_policy_path(policy_path)

    @property
    def label(self) -> str:
        return self._ref

    @contextmanager
    def materialize(self, *, keep: bool = False) -> Iterator[MaterializedPolicy]:
        toplevel = gitmod.find_toplevel(self._repo)
        sha = gitmod.rev_parse(toplevel, self._ref)
        with _private_tempdir(keep=keep) as root:
            gitmod.archive_to(toplevel, sha, self._policy_path, root)
            yield MaterializedPolicy(
                path=root / self._policy_path, sha=sha, label=self._ref, is_worktree=False
            )


class WorktreeSource:
    """Policy path copied from the live working tree (``--head WORKTREE``, AC-8.3)."""

    def __init__(self, repo: Path, policy_path: str) -> None:
        self._repo = repo
        self._policy_path = gitmod.normalize_policy_path(policy_path)

    @property
    def label(self) -> str:
        return WORKTREE

    @contextmanager
    def materialize(self, *, keep: bool = False) -> Iterator[MaterializedPolicy]:
        toplevel = gitmod.find_toplevel(self._repo)
        live = toplevel / self._policy_path
        if not live.exists():
            msg = f"policy path {self._policy_path!r} does not exist in the working tree"
            raise PolicyError(msg)
        with _private_tempdir(keep=keep) as root:
            dest = root / self._policy_path
            if live.is_dir():
                shutil.copytree(live, dest)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(live, dest)
            yield MaterializedPolicy(path=dest, sha=None, label=WORKTREE, is_worktree=True)


class DirectorySource:
    """A policy directory used as-is (bundled demo fixtures, tests). No git, no copy."""

    def __init__(self, path: Path, label: str) -> None:
        self._path = path
        self._label = label

    @property
    def label(self) -> str:
        return self._label

    @contextmanager
    def materialize(self, *, keep: bool = False) -> Iterator[MaterializedPolicy]:
        if not self._path.exists():
            msg = f"policy path {self._path} does not exist"
            raise PolicyError(msg)
        yield MaterializedPolicy(path=self._path, sha=None, label=self._label, is_worktree=False)


def source_for(repo: Path, ref: str, policy_path: str) -> PolicySource:
    """``WORKTREE`` selects the live tree; anything else is a git ref."""
    if ref == WORKTREE:
        return WorktreeSource(repo, policy_path)
    return GitRefSource(repo, ref, policy_path)
