// Demo policy, base version (Cedar). Mirrors rules.py and agent.rego.
@id("read")
permit(principal, action == Action::"github.read", resource);

@id("slack")
permit(principal, action == Action::"slack.post", resource);

@id("refund")
permit(principal, action == Action::"stripe.refund", resource);

@id("terminate")
permit(principal, action == Action::"aws.ec2.terminate_instance", resource)
when { context.call.principal.attrs has team && context.call.principal.attrs.team == "ops" };

@id("delete-branch")
forbid(principal, action == Action::"github.delete_branch", resource);

@id("salesforce")
permit(principal, action == Action::"salesforce.update", resource);
