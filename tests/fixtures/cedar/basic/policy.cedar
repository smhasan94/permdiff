// SOURCE: hand-written for permdiff tests, Cedar 4.x syntax, validated with cedarpy 4.12.1.
@id("read-free")
permit(principal, action == Action::"github.read", resource);

@id("refund-large")
@require_approval("finance review for refunds over 500")
forbid(principal, action == Action::"stripe.refund", resource)
when { context has amount && context.amount > 500 };

@id("refund-ok")
permit(principal, action == Action::"stripe.refund", resource);

@id("delete-prod")
forbid(principal, action == Action::"github.delete_branch", resource)
when { context has env && context.env == "prod" };

@id("delete-ok")
permit(principal, action == Action::"github.delete_branch", resource);

@id("sf-needs-dept")
permit(principal, action == Action::"salesforce.update", resource)
when { principal.department == "cs" };

@id("hours")
permit(principal, action == Action::"slack.post", resource)
when { context.now.toTime() >= duration("9h") && context.now.toTime() < duration("17h") };

@id("mixed-approval")
@require_approval("ops sign-off")
forbid(principal, action == Action::"aws.ec2.terminate_instance", resource);

@id("mixed-hard")
forbid(principal, action == Action::"aws.ec2.terminate_instance", resource)
when { context has env && context.env == "prod" };

@id("terminate-ok")
permit(principal, action == Action::"aws.ec2.terminate_instance", resource);
