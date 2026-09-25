"""Demo policy, base version: what is deployed today."""

from __future__ import annotations

from permdiff.demo.engine import Rule
from permdiff.models import ToolCall


def _is_ops(call: ToolCall) -> bool:
    return call.principal.attrs.get("team") == "ops"


DEFAULT = "deny"

RULES = (
    Rule(tool="github.read*", effect="allow"),
    Rule(tool="slack.post", effect="allow"),
    Rule(tool="stripe.refund", effect="allow"),
    Rule(tool="aws.ec2.terminate_instance", effect="allow", when=_is_ops, reason="ops team"),
    Rule(tool="github.delete_branch", effect="deny", reason="branch protection"),
    Rule(tool="salesforce.update", effect="allow"),
)
