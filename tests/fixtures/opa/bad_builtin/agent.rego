package agent.authz

import rego.v1

default decision := {"effect": "deny"}

decision := {"effect": "allow"} if {
    to_number(input.arguments.n) > 1
}
