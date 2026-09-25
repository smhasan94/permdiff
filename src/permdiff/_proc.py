"""Subprocess wrapper. Argument lists only, never a shell."""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from permdiff.errors import ProcError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcResult:
    """Outcome of one subprocess run."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run(
    argv: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    stdin: str | None = None,
    timeout: float | None = None,
) -> ProcResult:
    """Run ``argv`` without a shell and capture text output.

    Raises ProcError when the executable is missing; a non-zero exit is
    returned, not raised, so callers can attach context.
    """
    args = tuple(os.fspath(a) for a in argv)
    log.debug("run: %s (cwd=%s)", " ".join(args), cwd)
    try:
        completed = subprocess.run(  # noqa: S603  # argument list, no shell
            args,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        msg = f"executable not found: {args[0]}"
        raise ProcError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        msg = f"timed out after {timeout}s: {args[0]}"
        raise ProcError(msg) from exc
    log.debug("exit %d: %s", completed.returncode, args[0])
    return ProcResult(
        argv=args,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
