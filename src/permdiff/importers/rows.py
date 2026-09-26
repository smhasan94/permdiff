"""Row sources shared by the Langfuse and LangSmith importers.

One export can arrive as JSONL, a JSON array, an API page (``{"data": [...]}``), or
Parquet, optionally gzip-compressed for the text formats. ``iter_rows`` hides that behind
``(row, locator)`` pairs; Parquet needs the ``permdiff[parquet]`` extra (``pyarrow``).
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from permdiff.errors import TraceImportError
from permdiff.importers.limits import RecordRejected, check_line_size, decode_utf8

Row = Mapping[str, Any]
PARQUET_MAGIC = b"PAR1"
GZIP_MAGIC = b"\x1f\x8b"
PARQUET_HINT = 'reading Parquet needs the pyarrow extra: pip install "permdiff[parquet]"'


def parse_json_field(value: Any) -> Any:
    """Exports often store JSON columns as text; decode when it parses, else keep the text."""
    if not isinstance(value, str) or not value:
        return value
    stripped = value.lstrip()
    if not stripped or stripped[0] not in "{[":
        return value
    try:
        return json.loads(value)
    except ValueError:
        return value


def parquet_rows(path: Path) -> list[Row]:
    try:
        import pyarrow.parquet as pq  # type: ignore[import-untyped]  # noqa: PLC0415
    except ImportError as exc:
        msg = f"{path}: {PARQUET_HINT}"
        raise TraceImportError(msg) from exc
    try:
        table = pq.read_table(path)
    except (OSError, ValueError) as exc:
        msg = f"{path}: cannot read Parquet: {exc}"
        raise TraceImportError(msg) from exc
    rows: list[Any] = table.to_pylist()
    return [row for row in rows if isinstance(row, Mapping)]


def _read_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        msg = f"cannot read {path}: {exc.strerror or exc}"
        raise TraceImportError(msg) from exc
    if raw.startswith(GZIP_MAGIC):
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError) as exc:
            msg = f"{path}: cannot decompress: {exc}"
            raise TraceImportError(msg) from exc
    return decode_utf8(raw, locator=str(path))


def _is_parquet(path: Path) -> bool:
    if path.suffix.lower() == ".parquet":
        return True
    try:
        with path.open("rb") as fh:
            return fh.read(4) == PARQUET_MAGIC
    except OSError:
        return False


def _document_rows(document: Any, path: Path) -> list[Row] | None:
    """Rows of a whole-document JSON file, or ``None`` when the text is not one document."""
    if isinstance(document, Mapping) and isinstance(document.get("data"), list):
        document = document["data"]
    if isinstance(document, Mapping):
        return [document]
    if isinstance(document, list):
        if not all(isinstance(item, Mapping) for item in document):
            msg = f"{path}: expected rows (JSON objects) in the array"
            raise TraceImportError(msg)
        return list(document)
    msg = f'{path}: expected rows: a JSON array, an object, a {{"data": [...]}} page, or JSONL'
    raise TraceImportError(msg)


def iter_rows(path: Path) -> Iterator[tuple[Row | RecordRejected, str]]:
    """``(row, locator)``: ``path[i]`` for tabular files, ``path:lineno`` for JSONL."""
    if _is_parquet(path):
        for index, row in enumerate(parquet_rows(path)):
            yield row, f"{path}[{index}]"
        return
    text = _read_text(path)
    try:
        document = json.loads(text)
    except RecursionError as exc:
        msg = f"{path}: JSON nested too deeply"
        raise TraceImportError(msg) from exc
    except ValueError:
        document = None
    if document is not None:
        rows = _document_rows(document, path)
        if rows is not None:
            if len(rows) == 1 and isinstance(document, Mapping) and "data" not in document:
                yield rows[0], str(path)
                return
            for index, row in enumerate(rows):
                yield row, f"{path}[{index}]"
            return
    yield from _iter_lines(text, path)


def _iter_lines(text: str, path: Path) -> Iterator[tuple[Row | RecordRejected, str]]:
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        locator = f"{path}:{lineno}"
        try:
            check_line_size(line.encode("utf-8"))
            obj = json.loads(line)
        except RecordRejected as exc:
            yield exc, locator
            continue
        except (ValueError, RecursionError) as exc:
            yield RecordRejected(f"invalid JSON: {exc}"), locator
            continue
        if not isinstance(obj, Mapping):
            yield RecordRejected("expected a JSON object"), locator
            continue
        yield obj, locator
