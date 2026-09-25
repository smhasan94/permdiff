from __future__ import annotations

import pytest

from permdiff.errors import ConfigError
from permdiff.models import TransitionClass
from permdiff.report.grouping import GROUP_FIELDS, group_transitions, validate_group_by
from tests.report_fixtures import sample_report


def test_groups_are_sorted_widening_first_then_count_desc_then_key() -> None:
    groups = group_transitions(sample_report().transitions)

    assert [(g.cls, g.label, g.count) for g in groups] == [
        (TransitionClass.WIDENING, "github.delete_branch", 2),
        (TransitionClass.WIDENING, "stripe.refund", 1),
        (TransitionClass.TIGHTENING, "aws.ec2.terminate_instance", 3),
        (TransitionClass.TIGHTENING, "stripe.refund", 1),
        (TransitionClass.CANT_EVALUATE, "salesforce.update", 2),
    ]


def test_samples_are_capped_and_sorted_by_call_id() -> None:
    groups = group_transitions(sample_report().transitions, samples=2)
    tightening = next(g for g in groups if g.label == "aws.ec2.terminate_instance")

    assert [t.call.id for t in tightening.samples] == ["call-004", "call-005"]
    assert tightening.count == 3
    assert tightening.effects == "allow → deny"
    assert tightening.reasons == ("prod instances locked",)


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


def test_combinable_group_by_fields_label_as_pairs() -> None:
    groups = group_transitions(sample_report().transitions, by=("tool", "agent"))

    assert groups[0].label == "tool=github.delete_branch, agent=support-bot"
    assert groups[0].key.parts == (("tool", "github.delete_branch"), ("agent", "support-bot"))


def test_group_by_reason_resource_type_and_principal() -> None:
    by_reason = group_transitions(sample_report().transitions, by=("reason",))
    by_resource = group_transitions(sample_report().transitions, by=("resource.type",))
    by_principal = group_transitions(sample_report().transitions, by=("principal",))

    assert [g.label for g in by_reason if g.cls is TransitionClass.WIDENING] == [
        "reason=branch protection removed",
        "reason=amount>500",
    ]
    assert {g.label for g in by_resource} == {"resource.type=generic"}
    assert all(g.label.startswith("principal=") for g in by_principal)


def test_cant_evaluate_group_reason_comes_from_the_erroring_side() -> None:
    groups = group_transitions(sample_report().transitions, by=("reason",))
    errors = [g for g in groups if g.cls is TransitionClass.CANT_EVALUATE]

    assert [g.label for g in errors] == ["reason=principal.department"]


def test_group_counts_sum_to_class_counts() -> None:
    report = sample_report()
    groups = group_transitions(report.transitions, include_unchanged=True, include_attribution=True)

    for cls in TransitionClass:
        assert sum(g.count for g in groups if g.cls is cls) == report.counts.of(cls)


@pytest.mark.parametrize("bad", [("nope",), ("tool", "call.id")])
def test_unknown_group_field_names_flag_and_choices(bad: tuple[str, ...]) -> None:
    with pytest.raises(ConfigError, match="--group-by") as exc_info:
        validate_group_by(bad)

    assert all(field in str(exc_info.value) for field in GROUP_FIELDS)


def test_validate_group_by_dedupes_and_defaults() -> None:
    assert validate_group_by((" tool ", "agent", "tool")) == ("tool", "agent")
    assert validate_group_by(()) == ("tool",)
    assert validate_group_by(("",)) == ("tool",)


def test_empty_input_gives_no_groups() -> None:
    assert group_transitions(()) == ()
