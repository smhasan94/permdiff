from __future__ import annotations

from permdiff.report.summary import summary_rows
from tests.report_fixtures import sample_report


def test_summary_rows_match_the_overview_block_shape() -> None:
    rows = summary_rows(sample_report())

    assert [(r.label, r.count, r.detail, r.is_widening) for r in rows] == [
        ("newly DENIED", 3, "aws.ec2.terminate_instance", False),
        ("newly ALLOWED", 2, "github.delete_branch", True),
        ("now REQUIRE_APPROVAL", 2, "stripe.refund", True),
        ("attribution changed", 1, "github.read", False),
        ("can't evaluate", 2, "missing context: principal.department", False),
        ("unchanged", 4, "", False),
    ]


def test_empty_report_has_only_the_unchanged_row() -> None:
    report = sample_report().model_copy(update={"transitions": ()})
    report = report.model_copy(
        update={"counts": report.counts.model_copy(update={"evaluated": 0, "by_class": {}})}
    )

    rows = summary_rows(report)

    assert [(r.label, r.count) for r in rows] == [("unchanged", 0)]
