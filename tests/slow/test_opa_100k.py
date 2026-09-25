"""AC-10.2: 100K calls per ref through one ``opa eval`` in under 10 s."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from permdiff.evaluators.opa import OpaEvaluator, OpaOptions
from permdiff.models import Effect, ToolCall
from tests.conftest import OPA_FIXTURES

N = 100_000
BUDGET_SECONDS = 10.0


@pytest.mark.slow
def test_opa_evaluates_100k_calls_within_budget(opa_bin: Path) -> None:
    start_ts = datetime(2026, 9, 18, 8, tzinfo=UTC)
    calls = [
        ToolCall.model_validate(
            {
                "id": f"c{i}",
                "timestamp": (start_ts + timedelta(seconds=i)).isoformat(),
                "principal": {"id": f"user{i % 50}", "attrs": {"dept": "x"}},
                "agent": {"id": "bot"},
                "tool": {"name": ("github.read", "stripe.refund", "slack.post")[i % 3]},
                "arguments": {"amount": (i * 37) % 1000, "note": "x" * 40},
                "context": {"env": "prod"},
            }
        )
        for i in range(N)
    ]
    opa = OpaEvaluator(OpaOptions(opa_bin=opa_bin))
    prepared = opa.prepare(OPA_FIXTURES / "basic", label="b")

    started = time.perf_counter()
    decisions = opa.evaluate(prepared, calls)
    elapsed = time.perf_counter() - started

    assert len(decisions) == N
    assert decisions[0].effect is Effect.ALLOW
    assert elapsed < BUDGET_SECONDS, f"took {elapsed:.1f}s"
