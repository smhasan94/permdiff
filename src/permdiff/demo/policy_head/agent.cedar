// Demo policy, head version (Cedar). Mirrors rules.py and agent.rego.
@id("read")
permit(principal, action == Action::"github.read", resource);

@id("slack")
permit(principal, action == Action::"slack.post", resource);

@id("refund-large")
@require_approval("amount>500")
forbid(principal, action == Action::"stripe.refund", resource)
when { context has amount && context.amount > 500 };

@id("refund")
permit(principal, action == Action::"stripe.refund", resource);

@id("terminate")
forbid(principal, action == Action::"aws.ec2.terminate_instance", resource);

@id("delete-branch-nonprod")
permit(principal, action == Action::"github.delete_branch", resource)
when { context has env && context.env != "prod" };

@id("delete-branch")
forbid(principal, action == Action::"github.delete_branch", resource)
when { context has env && context.env == "prod" };

// The new rule reads an attribute the traces may lack: a missing one is reported, never guessed.
@id("salesforce")
permit(principal, action == Action::"salesforce.update", resource)
when { context.call.principal.attrs.department != "" };
