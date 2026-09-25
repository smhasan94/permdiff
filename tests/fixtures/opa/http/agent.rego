package agent.authz

import rego.v1

default decision := {"effect": "deny", "reason": "risk service said no"}

decision := {"effect": "allow", "reason": "low risk"} if {
    resp := http.send({"method": "get", "url": "https://risk.example/score"})
    resp.body.score < 50
}
