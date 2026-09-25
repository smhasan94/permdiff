"""Security invariants from the threat model (NFR-S2, NFR-S5)."""

from __future__ import annotations

import re
import stat
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from permdiff.evaluators.opa import OpaEvaluator, OpaOptions
from permdiff.models import ToolCall
from tests.conftest import OPA_FIXTURES

SRC = Path(__file__).parents[2] / "src" / "permdiff"
FORBIDDEN = re.compile(
    r"shell\s*=\s*True|os\.system\(|os\.popen\(|subprocess\.getoutput|eval\(|exec\("
)


def test_no_shell_execution_or_eval_in_the_package() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if FORBIDDEN.search(line) and "spec.loader.exec_module" not in line:
                offenders.append(f"{path.relative_to(SRC)}:{lineno}: {line.strip()}")
    assert offenders == []


def test_subprocess_wrapper_never_uses_a_shell() -> None:
    text = (SRC / "_proc.py").read_text(encoding="utf-8")

    assert "shell=" not in text.replace("Argument lists only, never a shell", "")
    assert "capture_output=True" in text


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_opa_batch_temp_dir_is_private(opa_bin: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []
    real_mkdtemp = tempfile.mkdtemp

    def spy(*args: Any, **kwargs: Any) -> Any:
        path = real_mkdtemp(*args, **kwargs)
        seen.append(stat.S_IMODE(Path(path).stat().st_mode))
        return path

    monkeypatch.setattr(tempfile, "mkdtemp", spy)
    opa = OpaEvaluator(OpaOptions(opa_bin=opa_bin))
    call = ToolCall.model_validate(
        {
            "id": "1",
            "timestamp": datetime(2026, 9, 20, tzinfo=UTC).isoformat(),
            "principal": {"id": "p"},
            "agent": {"id": "a"},
            "tool": {"name": "github.read"},
        }
    )

    opa.evaluate(opa.prepare(OPA_FIXTURES / "basic", label="b"), [call])

    assert seen and all(mode == 0o700 for mode in seen)
