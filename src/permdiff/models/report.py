"""Report envelope shared by every reporter (FR-13 footer counts, FR-22 allow-widening)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from pydantic import Field, model_validator

from permdiff.models.base import Frozen
from permdiff.models.transition import Transition, TransitionClass


class Counts(Frozen):
    """Footer numbers. ``evaluated`` equals the sum of ``by_class`` (AC-13.1)."""

    imported: int = 0
    skipped: int = 0
    filtered: int = 0
    evaluated: int = 0
    by_class: Mapping[TransitionClass, int] = Field(default_factory=dict)
    recorded_disagreements: int = 0

    @model_validator(mode="after")
    def _classes_sum_to_evaluated(self) -> Counts:
        total = sum(self.by_class.values())
        if total != self.evaluated:
            msg = f"by_class sums to {total} but evaluated is {self.evaluated}"
            raise ValueError(msg)
        return self

    def of(self, cls: TransitionClass) -> int:
        return self.by_class.get(cls, 0)


class ReportHeader(Frozen):
    base_label: str
    base_sha: str | None
    head_label: str
    head_sha: str | None
    is_worktree: bool
    policy_path: str
    engine: str
    window: tuple[datetime, datetime] | None = None
    salt: str
    undefined_policy: str | None = None
    generated_at: datetime


class Report(Frozen):
    header: ReportHeader
    transitions: tuple[Transition, ...]
    counts: Counts
    allow_widening: tuple[str, str] | None = None
    """``(reason, actor)`` when ``--allow-widening`` was given (AC-22.3)."""
