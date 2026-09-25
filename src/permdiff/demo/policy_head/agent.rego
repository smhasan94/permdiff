# Demo policy, head version: the proposed change under review. Mirrors rules.py.
package agent.authz

import rego.v1

refund_approval_threshold := 500

default decision := {"effect": "deny", "rule": "default"}

decision := {"effect": "allow", "rule": "read"} if startswith(input.tool.name, "github.read")

decision := {"effect": "allow", "rule": "slack"} if input.tool.name == "slack.post"

decision := {"effect": "require_approval", "reason": "amount>500", "rule": "refund-large"} if {
    input.tool.name == "stripe.refund"
    input.arguments.amount > refund_approval_threshold
}

decision := {"effect": "allow", "rule": "refund"} if {
    input.tool.name == "stripe.refund"
    input.arguments.amount <= refund_approval_threshold
}

decision := {"effect": "deny", "reason": "prod instances locked", "rule": "terminate"} if {
    input.tool.name == "aws.ec2.terminate_instance"
}

decision := {"effect": "allow", "reason": "non-prod cleanup", "rule": "delete-branch-nonprod"} if {
    input.tool.name == "github.delete_branch"
    input.context.env != "prod"
}

decision := {"effect": "deny", "reason": "branch protection", "rule": "delete-branch"} if {
    input.tool.name == "github.delete_branch"
    input.context.env == "prod"
}

decision := {"effect": "allow", "rule": "salesforce"} if {
    input.tool.name == "salesforce.update"
    input.principal.attrs.department
}

# The new rule needs an attribute the traces may lack: report it, never guess.
decision := {"effect": "error", "kind": "missing_context", "reason": "principal.attrs.department"} if {
    input.tool.name == "salesforce.update"
    not input.principal.attrs.department
}
