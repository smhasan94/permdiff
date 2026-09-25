# Demo policy, base version: what is deployed today. Mirrors rules.py.
package agent.authz

import rego.v1

default decision := {"effect": "deny", "rule": "default"}

decision := {"effect": "allow", "rule": "read"} if startswith(input.tool.name, "github.read")

decision := {"effect": "allow", "rule": "slack"} if input.tool.name == "slack.post"

decision := {"effect": "allow", "rule": "refund"} if input.tool.name == "stripe.refund"

decision := {"effect": "allow", "reason": "ops team", "rule": "terminate"} if {
    input.tool.name == "aws.ec2.terminate_instance"
    input.principal.attrs.team == "ops"
}

decision := {"effect": "deny", "reason": "branch protection", "rule": "delete-branch"} if {
    input.tool.name == "github.delete_branch"
}

decision := {"effect": "allow", "rule": "salesforce"} if input.tool.name == "salesforce.update"
