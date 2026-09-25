from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from permdiff.models import Decision, Effect, ToolCall, Transition
from permdiff.redact import Redactor
from permdiff.report.exit_codes import EXIT_GATE, EXIT_OK, FailOn, gate
from permdiff.report.markdown import MARKER, render_markdown
from permdiff.report.view import build_view
from tests.redaction_harness import assert_no_sentinels
from tests.report_fixtures import FIXED_SALT, sample_report

GOLDEN = Path(__file__).parents[2] / "golden" / "markdown_report.md"
GITHUB_COMMENT_LIMIT = 65_536


def _render(**view_kwargs: object) -> str:
    view = build_view(sample_report(), redactor=Redactor(salt=FIXED_SALT), **view_kwargs)  # type: ignore[arg-type]
    return render_markdown(view, exit_code=gate(view, FailOn.WIDEN), fail_on=FailOn.WIDEN)


def test_matches_golden() -> None:
    out = _render()
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(out, encoding="utf-8")

    assert out == GOLDEN.read_text(encoding="utf-8"), "rerun with UPDATE_GOLDEN=1 to accept"


def test_starts_with_marker_and_names_refs_shas_and_salt() -> None:
    out = _render()

    assert out.startswith(MARKER + "\n")
    assert "## permdiff: `origin/main` → `HEAD`" in out
    assert (
        "base `0123456789ab` · head `89abcdef0123` · salt `000102030405060708090a0b0c0d0e0f`" in out
    )
    assert "| newly ALLOWED ⚠ widening | 2 | `github.delete_branch` |" in out
    assert "**exit 2** (widening found; --fail-on widen)" in out


def test_one_collapsible_section_per_group_with_samples() -> None:
    out = _render(samples=1)

    assert out.count("<details>") == 5
    assert (
        "<summary>⚠ widening · <code>github.delete_branch</code> · 2 calls · deny → allow</summary>"
        in out
    )
    assert "…and 1 more" in out
    assert "| `call-001` | `principal:" in out


def test_byte_identical_for_identical_inputs() -> None:
    assert _render() == _render()


def test_safe_output_leaks_no_sentinels_and_hashes_principals() -> None:
    out = _render()

    assert_no_sentinels(out)
    assert "sentinel-principal" not in out
    assert "principal:" in out


def test_pipes_and_backticks_in_values_are_escaped() -> None:
    call = ToolCall.model_validate(
        {
            "id": "c|1",
            "timestamp": datetime(2026, 9, 20, tzinfo=UTC).isoformat(),
            "principal": {"id": "p"},
            "agent": {"id": "a"},
            "tool": {"name": "t`x|y"},
        }
    )
    base = Decision(call_id="c|1", effect=Effect.DENY, engine="e")
    head = Decision(call_id="c|1", effect=Effect.ALLOW, reasons=("a|b",), engine="e")
    report = sample_report().model_copy(
        update={"transitions": (Transition.build(call, base, head),)}
    )
    report = report.model_copy(
        update={
            "counts": report.counts.model_copy(update={"evaluated": 1, "by_class": {"widening": 1}})
        }
    )
    view = build_view(report, redactor=Redactor(salt=FIXED_SALT))

    out = render_markdown(view, exit_code=EXIT_GATE, fail_on=FailOn.WIDEN)

    assert "| `c\\|1` |" in out
    assert "t'x\\|y" in out
    assert "| a\\|b |" in out


def test_truncation_note_and_footer_details() -> None:
    out = _render(max_groups=2)
    allowed = build_view(
        sample_report(allow_widening=("ticket-9", "alice")), redactor=Redactor(salt=FIXED_SALT)
    )

    assert "…3 more groups not shown (--max-groups)" in out
    assert (
        "imported 17, skipped 3 malformed · recorded decisions disagree with base on 1 call" in out
    )
    allowed_out = render_markdown(allowed, exit_code=EXIT_OK, fail_on=FailOn.WIDEN)
    assert "allow-widening by alice: ticket-9" in allowed_out
    assert "**exit 0** (widening allowed by alice: ticket-9)" in allowed_out


def test_large_report_stays_under_github_limit_with_default_max_groups() -> None:
    base_report = sample_report()
    template = base_report.transitions[0]
    transitions = tuple(
        template.model_copy(
            update={
                "call": template.call.model_copy(
                    update={
                        "id": f"call-{i:05d}",
                        "tool": template.call.tool.model_copy(update={"name": f"tool.{i % 400}"}),
                    }
                )
            }
        )
        for i in range(2000)
    )
    report = base_report.model_copy(update={"transitions": transitions})
    report = report.model_copy(
        update={
            "counts": report.counts.model_copy(
                update={"evaluated": 2000, "by_class": {"widening": 2000}}
            )
        }
    )
    view = build_view(report, redactor=Redactor(salt=FIXED_SALT))

    out = render_markdown(view, exit_code=EXIT_GATE, fail_on=FailOn.WIDEN)

    assert len(out.encode("utf-8")) < GITHUB_COMMENT_LIMIT
    assert len(view.groups) == 50
    assert "…350 more groups not shown" in out
