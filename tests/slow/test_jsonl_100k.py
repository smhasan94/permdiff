"""AC-2.1: 100K JSONL lines import in under 20 s (NFR-P1 import budget)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from permdiff.importers.jsonl import JsonlImporter

N = 100_000
BUDGET_SECONDS = 20.0


@pytest.mark.slow
def test_reads_100k_lines_within_budget(tmp_path: Path) -> None:
    path = tmp_path / "big.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for i in range(N):
            fh.write(
                json.dumps(
                    {
                        "id": f"c{i}",
                        "timestamp": "2026-09-20T14:03:11.412Z",
                        "principal": {"id": f"user{i % 50}@example.com", "attrs": {"dept": "s"}},
                        "agent": {"id": "support-bot", "version": "1.4.0"},
                        "tool": {"name": f"tool.{i % 20}", "server": "mcp"},
                        "arguments": {"n": i, "s": "x" * 40, "l": [1, 2, 3]},
                        "resource": {"type": "thing", "id": str(i)},
                        "context": {"session_id": f"s{i % 1000}", "env": "prod"},
                    }
                )
            )
            fh.write("\n")

    start = time.perf_counter()
    result = JsonlImporter().read(path)
    elapsed = time.perf_counter() - start

    assert result.stats.read == N
    assert elapsed < BUDGET_SECONDS, f"took {elapsed:.1f}s"
