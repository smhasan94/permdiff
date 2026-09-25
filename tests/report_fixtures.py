"""A fixed, deterministic Report used by reporter snapshot and sentinel tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from permdiff.models import (
    Counts,
    Decision,
    Effect,
    ErrorKind,
    Report,
    ReportHeader,
    ToolCall,
    Transition,
    TransitionClass,
)
from tests.redaction_harness import SENTINELS

FIXED_SALT = bytes(range(16))
GENERATED_AT = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
_T0 = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)


def _call(n: int, tool: str, args: dict[str, Any] | None = None) -> ToolCall:
    return ToolCall.model_validate(
        {
            "id": f"call-{n:03d}",
            "timestamp": (_T0 + timedelta(hours=n * 7)).isoformat(),
            "principal": {
                "id": SENTINELS["principal_id"],
                "attrs": {"department": SENTINELS["principal_attr"]},
            },
            "agent": {"id": "support-bot", "version": "1.4.0"},
            "tool": {"name": tool},
            "arguments": args
            if args is not None
            else {"target": SENTINELS["arg_top"], "meta": {"n": SENTINELS["arg_nested"]}},
            "resource": {"type": "generic", "id": SENTINELS["resource_id"]},
            "context": {"cwd": SENTINELS["context"]},
        }
    )


def _d(
    call: ToolCall, effect: Effect, *reasons: str, determining: tuple[str, ...] = ("p",)
) -> Decision:
    return Decision(
        call_id=call.id, effect=effect, reasons=reasons, determining=determining, engine="opa"
    )


def _err(call: ToolCall, reason: str) -> Decision:
    return Decision.error(call.id, ErrorKind.MISSING_CONTEXT, reason, engine="opa")


def sample_report(*, allow_widening: tuple[str, str] | None = None) -> Report:
    n = iter(range(1, 100))
    specs: list[tuple[ToolCall, Decision, Decision]] = []
    for _ in range(2):
        c = _call(next(n), "github.delete_branch", {"branch": SENTINELS["arg_top"]})
        specs.append((c, _d(c, Effect.DENY), _d(c, Effect.ALLOW, "branch protection removed")))
    c = _call(next(n), "stripe.refund", {"amount": 750})
    specs.append((c, _d(c, Effect.DENY), _d(c, Effect.REQUIRE_APPROVAL, "amount>500")))
    for _ in range(3):
        c = _call(next(n), "aws.ec2.terminate_instance")
        specs.append((c, _d(c, Effect.ALLOW), _d(c, Effect.DENY, "prod instances locked")))
    c = _call(next(n), "stripe.refund", {"amount": 900})
    specs.append((c, _d(c, Effect.ALLOW), _d(c, Effect.REQUIRE_APPROVAL, "amount>500")))
    for _ in range(2):
        c = _call(next(n), "salesforce.update")
        specs.append((c, _d(c, Effect.ALLOW), _err(c, "principal.department")))
    c = _call(next(n), "github.read")
    specs.append(
        (
            c,
            _d(c, Effect.ALLOW, determining=("a.rego:1",)),
            _d(c, Effect.ALLOW, determining=("b.rego:2",)),
        )
    )
    for _ in range(4):
        c = _call(next(n), "github.read")
        specs.append((c, _d(c, Effect.ALLOW), _d(c, Effect.ALLOW)))

    transitions = tuple(Transition.build(c, b, h) for c, b, h in specs)
    by_class: dict[TransitionClass, int] = {}
    for t in transitions:
        by_class[t.cls] = by_class.get(t.cls, 0) + 1
    header = ReportHeader(
        base_label="origin/main",
        base_sha="0123456789abcdef0123456789abcdef01234567",
        head_label="HEAD",
        head_sha="89abcdef0123456789abcdef0123456789abcdef",
        is_worktree=False,
        policy_path="policy",
        engine="opa",
        salt=FIXED_SALT.hex(),
        generated_at=GENERATED_AT,
    )
    counts = Counts(
        imported=len(transitions) + 3,
        skipped=3,
        evaluated=len(transitions),
        by_class=by_class,
        recorded_disagreements=1,
    )
    return Report(
        header=header, transitions=transitions, counts=counts, allow_widening=allow_widening
    )
