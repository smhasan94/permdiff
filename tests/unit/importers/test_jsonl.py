from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from permdiff.errors import TraceImportError
from permdiff.importers.jsonl import FORMAT_NAME, JsonlImporter
from permdiff.models.limits import MAX_LINE_BYTES, MAX_NESTING

RECORD: dict[str, Any] = {
    "id": "c1",
    "timestamp": "2026-09-20T14:03:11Z",
    "principal": {"id": "alice"},
    "agent": {"id": "bot"},
    "tool": {"name": "stripe.refund"},
}


def _write(tmp_path: Path, lines: list[str | bytes], name: str = "t.jsonl") -> Path:
    path = tmp_path / name
    with path.open("wb") as fh:
        for line in lines:
            fh.write(line if isinstance(line, bytes) else line.encode("utf-8"))
            fh.write(b"\n")
    return path


def _record(**overrides: Any) -> str:
    return json.dumps({**RECORD, **overrides})


def test_reads_one_call_per_line_and_ignores_blank_lines(tmp_path: Path) -> None:
    path = _write(tmp_path, [_record(id="a"), "", _record(id="b"), "   "])

    result = JsonlImporter().read(path)

    assert [c.id for c in result.calls] == ["a", "b"]
    assert result.stats.read == 2
    assert result.stats.skipped == 0
    assert result.stats.skipped_locators == ()


def test_source_is_filled_with_file_and_line_when_absent(tmp_path: Path) -> None:
    path = _write(tmp_path, [_record(id="a"), _record(id="b")])

    result = JsonlImporter().read(path)

    assert result.calls[1].source is not None
    assert result.calls[1].source.format == FORMAT_NAME
    assert result.calls[1].source.locator == f"{path}:2"


def test_existing_source_is_preserved(tmp_path: Path) -> None:
    src = {"format": "custody.trace.v1", "locator": "orig:9"}
    path = _write(tmp_path, [_record(source=src)])

    result = JsonlImporter().read(path)

    assert result.calls[0].source is not None
    assert result.calls[0].source.locator == "orig:9"


def test_malformed_line_is_skipped_with_locator_by_default(tmp_path: Path) -> None:
    path = _write(tmp_path, [_record(id="a"), "{not json", _record(id="b")])

    result = JsonlImporter().read(path)

    assert [c.id for c in result.calls] == ["a", "b"]
    assert result.stats.skipped == 1
    assert result.stats.skipped_locators[0].startswith(f"{path}:2")


def test_malformed_line_aborts_in_strict_mode(tmp_path: Path) -> None:
    path = _write(tmp_path, [_record(id="a"), "{not json"])

    with pytest.raises(TraceImportError, match=rf"{path}:2"):
        JsonlImporter().read(path, strict=True)


def test_invalid_record_names_missing_field_and_line(tmp_path: Path) -> None:
    bad = {k: v for k, v in RECORD.items() if k != "tool"}
    path = _write(tmp_path, [json.dumps(bad)])

    with pytest.raises(TraceImportError, match="tool") as exc_info:
        JsonlImporter().read(path, strict=True)

    assert f"{path}:1" in str(exc_info.value)


def test_non_utf8_input_is_rejected_even_when_not_strict(tmp_path: Path) -> None:
    path = _write(tmp_path, [_record(id="a"), b'{"id": "\xff\xfe"}'])

    with pytest.raises(TraceImportError, match="UTF-8") as exc_info:
        JsonlImporter().read(path)

    assert f"{path}:2" in str(exc_info.value)


def test_oversize_line_is_rejected_not_truncated(tmp_path: Path) -> None:
    big = _record(id="a", arguments={"blob": "x" * MAX_LINE_BYTES})
    path = _write(tmp_path, [big, _record(id="b")])

    result = JsonlImporter().read(path)

    assert [c.id for c in result.calls] == ["b"]
    assert "1 MiB" in result.stats.skipped_locators[0]
    with pytest.raises(TraceImportError, match="1 MiB"):
        JsonlImporter().read(path, strict=True)


def test_nesting_beyond_limit_is_rejected_with_reason(tmp_path: Path) -> None:
    deep: Any = "leaf"
    for _ in range(MAX_NESTING + 1):
        deep = {"k": deep}
    path = _write(tmp_path, [_record(arguments=deep)])

    result = JsonlImporter().read(path)

    assert result.calls == ()
    assert "nesting" in result.stats.skipped_locators[0]


def test_corpus_over_max_records_aborts_with_cap_in_message(tmp_path: Path) -> None:
    path = _write(tmp_path, [_record(id=str(i)) for i in range(5)])

    with pytest.raises(TraceImportError, match="max_records=4"):
        JsonlImporter().read(path, max_records=4)


def test_corpus_at_max_records_is_accepted(tmp_path: Path) -> None:
    path = _write(tmp_path, [_record(id=str(i)) for i in range(4)])

    result = JsonlImporter().read(path, max_records=4)

    assert result.stats.read == 4


def test_missing_file_is_an_import_error(tmp_path: Path) -> None:
    with pytest.raises(TraceImportError, match=r"nope\.jsonl"):
        JsonlImporter().read(tmp_path / "nope.jsonl")


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (_record().encode(), True),
        (b"\n\n" + _record().encode(), True),
        (b'{"schema": "custody.trace.v1", "id": "x"}', False),
        (b'{"resourceSpans": []}', False),
        (b"not json at all", False),
        (b"", False),
        (b"[1, 2]", False),
    ],
)
def test_detect_recognizes_permdiff_records(head: bytes, expected: bool) -> None:
    assert JsonlImporter().detect(head) is expected
