from __future__ import annotations

from pathlib import Path

import pytest

from permdiff.errors import TraceImportError
from permdiff.importers.limits import RecordRejected
from permdiff.importers.lines import read_lines, read_lines_multi
from permdiff.models import ToolCall


def _call(n: int) -> ToolCall:
    return ToolCall.model_validate(
        {
            "id": f"c{n}",
            "timestamp": "2026-09-25T00:00:00Z",
            "principal": {"id": "u"},
            "agent": {"id": "a"},
            "tool": {"name": "t"},
        }
    )


def test_read_lines_multi_yields_every_call_of_a_line(tmp_path: Path) -> None:
    path = tmp_path / "in.txt"
    path.write_text("2\n\n0\nbad\n1\n")

    def parse(text: str, locator: str) -> tuple[ToolCall, ...]:
        if text == "bad":
            raise RecordRejected("nope")
        return tuple(_call(i) for i in range(int(text)))

    result = read_lines_multi(path, parse)

    assert [c.id for c in result.calls] == ["c0", "c1", "c0"]
    assert result.stats.read == 3
    assert result.stats.skipped == 1
    assert result.stats.skipped_locators == (f"{path}:4: nope",)


def test_read_lines_multi_cap_counts_calls_not_lines(tmp_path: Path) -> None:
    path = tmp_path / "in.txt"
    path.write_text("3\n")

    with pytest.raises(TraceImportError, match="max_records=2"):
        read_lines_multi(path, lambda text, _: tuple(_call(i) for i in range(3)), max_records=2)


def test_read_lines_still_accepts_single_call_parsers(tmp_path: Path) -> None:
    path = tmp_path / "in.txt"
    path.write_text("x\nskip\n")

    result = read_lines(path, lambda text, _: None if text == "skip" else _call(0))

    assert result.stats.read == 1
    assert result.stats.skipped == 0
