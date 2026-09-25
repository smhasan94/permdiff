from __future__ import annotations

from permdiff.models import TransitionClass
from permdiff.report.grouping import group_transitions
from tests.report_fixtures import sample_report


def test_groups_are_sorted_widening_first_then_count_desc_then_key() -> None:
    groups = group_transitions(sample_report().transitions)

    assert [(g.cls, g.key, g.count) for g in groups] == [
        (TransitionClass.WIDENING, "github.delete_branch", 2),
        (TransitionClass.WIDENING, "stripe.refund", 1),
        (TransitionClass.TIGHTENING, "aws.ec2.terminate_instance", 3),
        (TransitionClass.TIGHTENING, "stripe.refund", 1),
        (TransitionClass.CANT_EVALUATE, "salesforce.update", 2),
    ]


def test_samples_are_capped_and_sorted_by_call_id() -> None:
    groups = group_transitions(sample_report().transitions, samples=2)
    tightening = next(g for g in groups if g.key == "aws.ec2.terminate_instance")

    assert [t.call.id for t in tightening.samples] == ["call-004", "call-005"]
    assert tightening.count == 3
    assert tightening.effects == "allow → deny"


def test_unchanged_and_attribution_are_opt_in() -> None:
    default = group_transitions(sample_report().transitions)
    everything = group_transitions(
        sample_report().transitions, include_unchanged=True, include_attribution=True
    )

    assert {g.cls for g in default} == {
        TransitionClass.WIDENING,
        TransitionClass.TIGHTENING,
        TransitionClass.CANT_EVALUATE,
    }
    assert TransitionClass.UNCHANGED in {g.cls for g in everything}
    assert TransitionClass.ATTRIBUTION_CHANGE in {g.cls for g in everything}


def test_empty_input_gives_no_groups() -> None:
    assert group_transitions(()) == ()
