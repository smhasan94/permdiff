"""AC-11.3: 100K calls per ref through cedarpy batches; the number goes in the README."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest

from permdiff.models import Effect, ToolCall
from tests.conftest import OPA_FIXTURES

pytest.importorskip("cedarpy")

from permdiff.evaluators.cedar.evaluator import CedarEvaluator

N = 100_000
BUDGET_SECONDS = 60.0


@pytest.mark.slow
def test_cedar_evaluates_100k_calls(
    opa_bin: object,
) -> None:  # opa_bin unused; keeps fixture wiring uniform
    start_ts = datetime(2026, 9, 18, 8, tzinfo=UTC)
    calls = [
        ToolCall.model_validate(
            {
                "id": f"c{i}",
                "timestamp": (start_ts + timedelta(seconds=i)).isoformat(),
                "principal": {"id": "alice"},
                "agent": {"id": "bot"},
                "tool": {"name": ("github.read", "stripe.refund", "slack.post")[i % 3]},
                "arguments": {"amount": (i * 37) % 1000},
                "resource": {"type": "thing", "id": "r1"},
                "context": {"env": "prod"},
            }
        )
        for i in range(N)
    ]
    cedar = CedarEvaluator()
    prepared = cedar.prepare(OPA_FIXTURES.parent / "cedar" / "basic", label="b")

    started = time.perf_counter()
    decisions = cedar.evaluate(prepared, calls)
    elapsed = time.perf_counter() - started

    assert len(decisions) == N
    assert decisions[0].effect is Effect.ALLOW
    print(f"\ncedar 100K: {elapsed:.1f}s")
    assert elapsed < BUDGET_SECONDS, f"took {elapsed:.1f}s"
