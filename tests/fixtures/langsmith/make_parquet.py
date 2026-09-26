"""Regenerate runs.parquet from runs.jsonl (needs the parquet extra)."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

HERE = Path(__file__).parent
rows = [json.loads(line) for line in (HERE / "runs.jsonl").read_text().splitlines() if line]
for row in rows:  # bulk exports store JSON columns as text
    for key in ("inputs", "outputs", "extra"):
        value = row[key]
        row[key] = value if value is None or isinstance(value, str) else json.dumps(value)
pq.write_table(pa.Table.from_pylist(rows), HERE / "runs.parquet")
