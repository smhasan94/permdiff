package agent.authz

import rego.v1

default decision := {"effect": "deny"}

decision := {"effect": "allow", "reason": "lucky"} if {
    rand.intn("dice", 6) >= 3
}
