"""Exit codes and the ``--fail-on`` gate (FR-22)."""

from __future__ import annotations

from enum import StrEnum

from permdiff.errors import EXIT_GATE, EXIT_OK, EXIT_TOOL_ERROR
from permdiff.models import CHANGE_CLASSES, Report, TransitionClass

__all__ = ["EXIT_GATE", "EXIT_OK", "EXIT_TOOL_ERROR", "FailOn", "gate", "gate_reason"]


class FailOn(StrEnum):
    WIDEN = "widen"
    ANY_CHANGE = "any-change"
    CANT_EVALUATE = "cant-evaluate"
    NONE = "none"


def _matched_classes(report: Report, fail_on: FailOn) -> tuple[TransitionClass, ...]:
    """Classes with a non-zero count that ``fail_on`` cares about, honoring ``--allow-widening``."""
    if fail_on is FailOn.NONE:
        return ()
    if fail_on is FailOn.WIDEN:
        wanted: tuple[TransitionClass, ...] = (TransitionClass.WIDENING,)
    elif fail_on is FailOn.CANT_EVALUATE:
        wanted = (TransitionClass.CANT_EVALUATE,)
    else:
        wanted = tuple(cls for cls in TransitionClass if cls in CHANGE_CLASSES)
    matched = [cls for cls in wanted if report.counts.of(cls) > 0]
    if report.allow_widening is not None:
        matched = [cls for cls in matched if cls is not TransitionClass.WIDENING]
    return tuple(matched)


def gate(report: Report, fail_on: FailOn) -> int:
    """``EXIT_GATE`` when the report matches ``fail_on``, else ``EXIT_OK`` (AC-22.1, AC-22.3)."""
    return EXIT_GATE if _matched_classes(report, fail_on) else EXIT_OK


def gate_reason(report: Report, fail_on: FailOn) -> str:
    """Footer sentence such as ``widening found; --fail-on widen``."""
    matched = _matched_classes(report, fail_on)
    if matched:
        found = ", ".join(cls.value.replace("_", " ") for cls in matched)
        return f"{found} found; --fail-on {fail_on.value}"
    if report.allow_widening is not None and report.counts.of(TransitionClass.WIDENING):
        reason, actor = report.allow_widening
        return f"widening allowed by {actor}: {reason}"
    return f"nothing matched --fail-on {fail_on.value}"
