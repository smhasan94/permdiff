package agent.authz

import rego.v1

decision := {"effect": "allow"} if input.tool.name == "github.read"
