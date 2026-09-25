package agent.authz

import rego.v1

default decision := {"effect": "deny", "reason": "default deny", "rule": "default"}

decision := {"effect": "allow", "reason": "reads are free", "rule": "read"} if {
    input.tool.name == "github.read"
}

decision := {"effect": "require_approval", "reasons": ["amount>500", "finance review"], "rules": ["refund-large", "finance"]} if {
    input.tool.name == "stripe.refund"
    input.arguments.amount > 500
}

decision := {"effect": "allow", "rule": "refund-small"} if {
    input.tool.name == "stripe.refund"
    input.arguments.amount <= 500
}

decision := {"effect": "permit"} if {
    input.tool.name == "weird.tool"
}

decision := "deny" if {
    input.tool.name == "string.tool"
}
