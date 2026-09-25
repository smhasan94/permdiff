from __future__ import annotations

from permdiff.models import TransitionClass
from permdiff.redact import RedactLevel, Redactor
from permdiff.report.view import build_view
from tests.redaction_harness import assert_no_sentinels
from tests.report_fixtures import FIXED_SALT, sample_report


def test_view_is_redacted_grouped_and_summarized() -> None:
    view = build_view(sample_report(), redactor=Redactor(salt=FIXED_SALT))

    assert view.header.salt == FIXED_SALT.hex()
    assert [g.cls for g in view.groups][:2] == [TransitionClass.WIDENING, TransitionClass.WIDENING]
    assert view.summary[-1].label == "unchanged"
    assert view.truncated_groups == 0
    assert view.group_by == ("tool",)
    assert_no_sentinels(view.model_dump_json())


def test_view_truncates_groups_beyond_max_groups() -> None:
    view = build_view(sample_report(), redactor=Redactor(salt=FIXED_SALT), max_groups=2)

    assert len(view.groups) == 2
    assert view.truncated_groups == 3


def test_view_groups_on_hashed_principals_so_counts_are_exact() -> None:
    view = build_view(sample_report(), redactor=Redactor(salt=FIXED_SALT), by=("principal",))

    assert all(g.label.startswith("principal=principal:") for g in view.groups)


def test_view_show_attribution_adds_the_group() -> None:
    view = build_view(sample_report(), redactor=Redactor(salt=FIXED_SALT), show_attribution=True)

    assert TransitionClass.ATTRIBUTION_CHANGE in {g.cls for g in view.groups}


def test_view_none_level_keeps_raw_values() -> None:
    view = build_view(
        sample_report(), redactor=Redactor(level=RedactLevel.NONE), include_decisions=True
    )

    assert view.transitions[0].call.principal.id.startswith("sentinel-principal")
    assert view.groups[0].samples[0].call.principal.id.startswith("sentinel-principal")


def test_view_without_decisions_keeps_no_transitions_but_redacts_samples() -> None:
    view = build_view(sample_report(), redactor=Redactor(salt=FIXED_SALT))

    assert view.transitions == ()
    assert view.groups[0].samples[0].call.principal.id.startswith("principal:")
    assert view.window is not None


def test_view_records_the_validated_group_by() -> None:
    view = build_view(sample_report(), redactor=Redactor(salt=FIXED_SALT), by=("", " "))

    assert view.group_by == ("tool",)
