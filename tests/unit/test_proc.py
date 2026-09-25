from __future__ import annotations

import sys
from pathlib import Path

import pytest

from permdiff._proc import run
from permdiff.errors import ProcError


def test_run_captures_stdout_and_exit_code() -> None:
    # Arrange
    argv = [sys.executable, "-c", "import sys; print('hi'); sys.exit(3)"]

    # Act
    result = run(argv)

    # Assert
    assert result.returncode == 3
    assert result.stdout.strip() == "hi"
    assert not result.ok


def test_run_ok_when_zero_exit() -> None:
    result = run([sys.executable, "-c", "pass"])
    assert result.ok


def test_run_passes_stdin_and_cwd(tmp_path: Path) -> None:
    result = run(
        [sys.executable, "-c", "import os,sys; print(os.getcwd()); print(sys.stdin.read())"],
        cwd=tmp_path,
        stdin="payload",
    )
    lines = result.stdout.splitlines()
    assert Path(lines[0]).resolve() == tmp_path.resolve()
    assert lines[1] == "payload"


def test_run_raises_proc_error_naming_missing_executable() -> None:
    with pytest.raises(ProcError, match="executable not found: definitely-not-a-binary-xyz"):
        run(["definitely-not-a-binary-xyz"])


def test_run_raises_proc_error_on_timeout() -> None:
    with pytest.raises(ProcError, match="timed out"):
        run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2)


def test_run_does_not_interpret_shell_metacharacters() -> None:
    marker = "$(echo injected)"
    result = run([sys.executable, "-c", "import sys; print(sys.argv[1])", marker])
    assert result.stdout.strip() == marker
