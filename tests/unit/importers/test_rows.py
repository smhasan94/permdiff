from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

from permdiff.errors import TraceImportError
from permdiff.importers.limits import RecordRejected
from permdiff.importers.rows import iter_rows, parse_json_field

ROWS = [{"id": "r1", "n": 1}, {"id": "r2", "nested": {"k": [1, 2]}}]


def _collect(path: Path) -> list[tuple[object, str]]:
    return [(row, loc) for row, loc in iter_rows(path)]


def test_jsonl_rows_and_bad_lines(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text('{"id": "r1", "n": 1}\n\n{oops\n[1]\n{"id": "r2"}\n')

    rows = _collect(path)

    assert rows[0] == ({"id": "r1", "n": 1}, f"{path}:1")
    assert isinstance(rows[1][0], RecordRejected)
    assert "invalid JSON" in rows[1][0].reason
    assert rows[1][1] == f"{path}:3"
    assert isinstance(rows[2][0], RecordRejected)
    assert "expected a JSON object" in rows[2][0].reason
    assert rows[3] == ({"id": "r2"}, f"{path}:5")


def test_json_array_and_data_envelope(tmp_path: Path) -> None:
    array = tmp_path / "rows.json"
    array.write_text(json.dumps(ROWS))
    envelope = tmp_path / "page.json"
    envelope.write_text(json.dumps({"data": ROWS, "meta": {"cursor": "x"}}))

    assert _collect(array) == [(ROWS[0], f"{array}[0]"), (ROWS[1], f"{array}[1]")]
    assert _collect(envelope) == [(ROWS[0], f"{envelope}[0]"), (ROWS[1], f"{envelope}[1]")]


def test_single_object_is_one_row_and_other_documents_are_errors(tmp_path: Path) -> None:
    single = tmp_path / "one.json"
    single.write_text(json.dumps(ROWS[0]))
    assert _collect(single) == [(ROWS[0], str(single))]

    scalar = tmp_path / "scalar.json"
    scalar.write_text("42")
    with pytest.raises(TraceImportError, match="expected rows"):
        _collect(scalar)

    mixed = tmp_path / "mixed.json"
    mixed.write_text("[1, {}]")
    with pytest.raises(TraceImportError, match="expected rows"):
        _collect(mixed)


def test_gzip_jsonl_is_decompressed(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for row in ROWS:
            fh.write(json.dumps(row) + "\n")

    assert [row for row, _ in _collect(path)] == ROWS


def test_parquet_rows_round_trip(tmp_path: Path) -> None:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    uniform = [
        {"id": "r1", "n": 1, "nested": {"k": [1, 2]}, "text": '{"a": 1}'},
        {"id": "r2", "n": 2, "nested": {"k": [3]}, "text": "plain"},
    ]
    path = tmp_path / "rows.parquet"
    pq.write_table(pa.Table.from_pylist(uniform), path)

    rows = _collect(path)

    assert [row for row, _ in rows] == uniform
    assert [loc for _, loc in rows] == [f"{path}[0]", f"{path}[1]"]


def test_parquet_without_pyarrow_names_the_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rows.parquet"
    path.write_bytes(b"PAR1" + b"\x00" * 16 + b"PAR1")
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", None)

    with pytest.raises(TraceImportError, match=r"permdiff\[parquet\]"):
        _collect(path)


def test_parse_json_field() -> None:
    assert parse_json_field('{"a": 1}') == {"a": 1}
    assert parse_json_field("[1, 2]") == [1, 2]
    assert parse_json_field("not json") == "not json"
    assert parse_json_field({"a": 1}) == {"a": 1}
    assert parse_json_field(None) is None
    assert parse_json_field("") == ""
