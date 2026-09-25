"""Demo policy, head version: the proposed change under review (comment check)."""

from __future__ import annotations

from permdiff.demo.engine import Rule
from permdiff.models import ToolCall

REFUND_APPROVAL_THRESHOLD = 500


def _large_refund(call: ToolCall) -> bool:
    amount = (call.arguments or {}).get("amount", 0)
    return isinstance(amount, int | float) and amount > REFUND_APPROVAL_THRESHOLD


def _not_prod(call: ToolCall) -> bool:
    return call.context.get("env") != "prod"


DEFAULT = "deny"

RULES = (
    Rule(tool="github.read*", effect="allow"),
    Rule(tool="slack.post", effect="allow"),
    Rule(tool="stripe.refund", effect="require_approval", when=_large_refund, reason="amount>500"),
    Rule(tool="stripe.refund", effect="allow"),
    Rule(tool="aws.ec2.terminate_instance", effect="deny", reason="prod instances locked"),
    Rule(tool="github.delete_branch", effect="allow", when=_not_prod, reason="non-prod cleanup"),
    Rule(tool="github.delete_branch", effect="deny", reason="branch protection"),
    Rule(tool="salesforce.update", effect="allow", requires=("principal.attrs.department",)),
)
