"""git helpers for policy loading (FR-8). Argument lists only, never a shell."""

from __future__ import annotations

import logging
import posixpath
import re
import tarfile
from pathlib import Path

from permdiff import _proc
from permdiff.errors import PolicyError

log = logging.getLogger(__name__)

SHALLOW_HINT = (
    "this looks like a shallow clone; in GitHub Actions set `fetch-depth: 0` "
    "on actions/checkout so both refs are present"
)


def normalize_policy_path(policy_path: str) -> str:
    """A repo-relative POSIX path with no ``..`` and no leading slash."""
    cleaned = posixpath.normpath(policy_path.strip().replace("\\", "/"))
    if not policy_path.strip() or cleaned in {".", ""}:
        msg = f"policy path {policy_path!r} is empty; pass --policy <dir>"
        raise PolicyError(msg)
    if cleaned.startswith(("/", "../")) or cleaned == ".." or re.match(r"^[A-Za-z]:", cleaned):
        msg = f"policy path {policy_path!r} must be relative to the repo and stay inside it"
        raise PolicyError(msg)
    return cleaned


def find_toplevel(path: Path) -> Path:
    """Repository root containing ``path`` (works from any subdirectory)."""
    result = _proc.run(["git", "rev-parse", "--show-toplevel"], cwd=path)
    if not result.ok:
        msg = f"{path}: not a git repository ({result.stderr.strip()})"
        raise PolicyError(msg)
    return Path(result.stdout.strip()).resolve()


def rev_parse(repo: Path, ref: str) -> str:
    """Full commit SHA for ``ref``; rejects option-looking refs before git runs (AC-8.1)."""
    if not ref or ref.startswith("-"):
        msg = f"invalid ref {ref!r} for --base/--head: must not be empty or start with '-'"
        raise PolicyError(msg)
    result = _proc.run(
        ["git", "rev-parse", "--verify", "--quiet", "--end-of-options", f"{ref}^{{commit}}"],
        cwd=repo,
    )
    if not result.ok:
        detail = result.stderr.strip() or "unknown revision"
        msg = f"cannot resolve ref {ref!r} for --base/--head: {detail}"
        if _is_shallow(repo):
            msg = f"{msg}; {SHALLOW_HINT}"
        raise PolicyError(msg)
    return result.stdout.strip()


def _is_shallow(repo: Path) -> bool:
    result = _proc.run(["git", "rev-parse", "--is-shallow-repository"], cwd=repo)
    return result.ok and result.stdout.strip() == "true"


def archive_to(repo: Path, sha: str, policy_path: str, dest: Path) -> None:
    """Extract ``policy_path`` at ``sha`` into ``dest`` via ``git archive`` (AC-8.2)."""
    tar_path = dest / "policy.tar"
    result = _proc.run(
        ["git", "archive", "--format=tar", f"--output={tar_path}", sha, "--", policy_path],
        cwd=repo,
    )
    if not result.ok:
        detail = result.stderr.strip()
        if "did not match any files" in detail or "not a valid object" in detail:
            msg = f"policy path {policy_path!r} is missing at ref {sha[:12]}"
        else:
            msg = f"git archive failed for {policy_path!r} at {sha[:12]}: {detail}"
        raise PolicyError(msg)
    with tarfile.open(tar_path) as tar:
        tar.extractall(dest, filter="data")
    tar_path.unlink()
    log.debug("extracted %s@%s to %s", policy_path, sha[:12], dest)
