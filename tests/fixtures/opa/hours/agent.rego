package agent.authz

import rego.v1

default decision := {"effect": "require_approval", "reason": "outside business hours"}

decision := {"effect": "allow", "reason": "business hours"} if {
    hour := time.clock([time.now_ns(), "UTC"])[0]
    hour >= 9
    hour < 17
}
