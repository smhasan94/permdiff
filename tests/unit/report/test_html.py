from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path

from permdiff.models import Decision, Effect, ToolCall, Transition
from permdiff.redact import Redactor
from permdiff.report.exit_codes import EXIT_GATE, FailOn, gate
from permdiff.report.html import render_html
from permdiff.report.view import build_view
from tests.redaction_harness import assert_no_sentinels
from tests.report_fixtures import FIXED_SALT, sample_report

GOLDEN = Path(__file__).parents[2] / "golden" / "html_report.html"


def _render(**view_kwargs: object) -> str:
    view = build_view(sample_report(), redactor=Redactor(salt=FIXED_SALT), **view_kwargs)  # type: ignore[arg-type]
    return render_html(view, exit_code=gate(view, FailOn.WIDEN), fail_on=FailOn.WIDEN)


def test_matches_golden() -> None:
    out = _render()
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(out, encoding="utf-8")

    assert out == GOLDEN.read_text(encoding="utf-8"), "rerun with UPDATE_GOLDEN=1 to accept"


def test_is_one_self_contained_document() -> None:
    out = _render()

    assert out.startswith("<!DOCTYPE html>")
    assert out.count("<html") == 1
    assert "<script" not in out.lower()
    assert re.search(r'(href|src)\s*=\s*"(https?:|//)', out) is None
    assert "<style>" in out
    assert "</html>" in out


def test_header_summary_groups_and_footer_are_present() -> None:
    out = _render()

    assert "permdiff: " in out
    assert "<table" in out
    assert "widening" in out
    assert "github.delete_branch" in out
    assert '<details open class="widening">' in out  # widening groups start expanded
    assert '<details class="group">' in out  # the others collapsed
    assert "exit 2" in out
    assert "widening found" in out


def test_values_are_html_escaped_and_locations_follow_reasons() -> None:
    call = ToolCall.model_validate(
        {
            "id": "c<1>",
            "timestamp": datetime(2026, 9, 20, tzinfo=UTC).isoformat(),
            "principal": {"id": "p"},
            "agent": {"id": "a"},
            "tool": {"name": "t<b>&x"},
            "arguments": {"cmd": "<img src=x onerror=alert(1)>"},
        }
    )
    base = Decision(call_id="c<1>", effect=Effect.DENY, engine="opa")
    head = Decision(
        call_id="c<1>",
        effect=Effect.ALLOW,
        reasons=("a<b & c",),
        locations=("agent.rego:7",),
        engine="opa",
    )
    report = sample_report().model_copy(
        update={"transitions": (Transition.build(call, base, head),)}
    )
    report = report.model_copy(
        update={
            "counts": report.counts.model_copy(update={"evaluated": 1, "by_class": {"widening": 1}})
        }
    )
    view = build_view(report, redactor=Redactor(salt=FIXED_SALT, show_args=frozenset({"cmd"})))

    out = render_html(view, exit_code=EXIT_GATE, fail_on=FailOn.WIDEN)

    assert "<img" not in out
    assert "&lt;img src=x onerror=alert(1)&gt;" in out
    assert "t&lt;b&gt;&amp;x" in out
    assert "c&lt;1&gt;" in out
    assert "a&lt;b &amp; c @ agent.rego:7" in out


def test_byte_identical_and_leaks_no_sentinels() -> None:
    first, second = _render(), _render()

    assert first == second
    assert_no_sentinels(first)
    assert "principal:" in first  # hashed principals, never verbatim


def test_truncation_note() -> None:
    out = _render(max_groups=2)

    assert "more groups not shown" in out
