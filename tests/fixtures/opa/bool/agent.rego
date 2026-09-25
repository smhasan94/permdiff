package agent.authz

import rego.v1

default allow := false

allow if input.tool.name == "github.read"
