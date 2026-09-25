from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from permdiff.models import Report
from permdiff.redact import Redactor
from permdiff.report.exit_codes import EXIT_GATE, EXIT_OK, FailOn, gate
from permdiff.report.terminal import render_terminal
from tests.redaction_harness import SENTINELS, assert_no_sentinels
from tests.report_fixtures import FIXED_SALT, sample_report

GOLDEN = Path(__file__).parents[2] / "golden"


def _check_golden(name: str, actual: str) -> None:
    path = GOLDEN / name
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(actual, encoding="utf-8")
    expected = path.read_text(encoding="utf-8")
    assert actual == expected, f"{name} differs; rerun with UPDATE_GOLDEN=1 to accept"


def _redacted(report: Report | None = None) -> Report:
    return Redactor(salt=FIXED_SALT, show_principal=True).report(report or sample_report())


def test_full_output_matches_golden() -> None:
    report = _redacted()

    out = render_terminal(report, exit_code=gate(report, FailOn.WIDEN), fail_on=FailOn.WIDEN)

    _check_golden("terminal_full.txt", out)


def test_quiet_output_matches_golden_and_has_no_groups() -> None:
    report = _redacted()

    out = render_terminal(report, exit_code=EXIT_GATE, fail_on=FailOn.WIDEN, quiet=True)

    _check_golden("terminal_quiet.txt", out)
    assert "call-001" not in out


def test_plain_output_has_no_ansi_escapes() -> None:
    out = render_terminal(_redacted(), exit_code=EXIT_GATE, fail_on=FailOn.WIDEN)

    assert "\x1b[" not in out


def test_color_output_has_ansi_escapes_and_same_text() -> None:
    plain = render_terminal(_redacted(), exit_code=EXIT_GATE, fail_on=FailOn.WIDEN)

    colored = render_terminal(_redacted(), exit_code=EXIT_GATE, fail_on=FailOn.WIDEN, color=True)

    assert "\x1b[" in colored
    assert re.sub(r"\x1b\[[0-9;]*m", "", colored) == plain


def test_safe_output_leaks_no_sentinels_except_terminal_principal() -> None:
    out = render_terminal(_redacted(), exit_code=EXIT_GATE, fail_on=FailOn.WIDEN)

    assert_no_sentinels(out, exclude=("principal_id",))
    assert SENTINELS["principal_id"] in out


def test_hashed_principal_when_not_shown() -> None:
    report = Redactor(salt=FIXED_SALT).report(sample_report())

    out = render_terminal(report, exit_code=EXIT_GATE, fail_on=FailOn.WIDEN)

    assert_no_sentinels(out)
    assert "principal:" in out


def test_footer_reflects_allow_widening_and_exit_zero() -> None:
    report = _redacted(sample_report(allow_widening=("ticket-42", "alice")))
    code = gate(report, FailOn.WIDEN)

    out = render_terminal(report, exit_code=code, fail_on=FailOn.WIDEN, quiet=True)

    assert code == EXIT_OK
    assert "allow-widening by alice: ticket-42" in out
    assert "exit 0 (widening allowed by alice: ticket-42)" in out


def test_worktree_head_is_labelled(tmp_path: Path) -> None:
    report = _redacted().model_copy(
        update={
            "header": sample_report().header.model_copy(
                update={"head_label": "WORKTREE", "head_sha": None, "is_worktree": True}
            )
        }
    )

    out = render_terminal(report, exit_code=EXIT_GATE, fail_on=FailOn.WIDEN, quiet=True)

    assert "origin/main → WORKTREE" in out
    assert "head WORKTREE" in out


def test_empty_report_renders_without_window() -> None:
    empty = sample_report().model_copy(update={"transitions": ()})
    empty = empty.model_copy(
        update={"counts": empty.counts.model_copy(update={"evaluated": 0, "by_class": {}})}
    )

    out = render_terminal(empty, exit_code=EXIT_OK, fail_on=FailOn.WIDEN)

    assert "(0 calls)" in out
    assert "unchanged" in out


@pytest.mark.parametrize("samples", [1, 3])
def test_more_marker_when_group_exceeds_samples(samples: int) -> None:
    out = render_terminal(_redacted(), exit_code=EXIT_GATE, fail_on=FailOn.WIDEN, samples=samples)

    assert ("… 2 more" in out) == (samples == 1)


def test_footer_shows_filtered_count_and_header_window() -> None:
    base = _redacted()
    report = base.model_copy(
        update={
            "counts": base.counts.model_copy(update={"filtered": 5, "skipped": 0}),
            "header": base.header.model_copy(
                update={
                    "window": (
                        datetime(2026, 9, 1, tzinfo=UTC),
                        datetime(2026, 9, 30, tzinfo=UTC),
                    )
                }
            ),
        }
    )

    out = render_terminal(report, exit_code=EXIT_GATE, fail_on=FailOn.WIDEN, quiet=True)

    assert "imported 17, filtered 5" in out
    assert "2026-09-01 → 2026-09-30" in out
