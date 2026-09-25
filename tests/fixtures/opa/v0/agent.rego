package agent.authz

default decision = {"effect": "deny"}

decision = {"effect": "allow"} { input.tool.name == "github.read" }
