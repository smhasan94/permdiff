"""Canonical data models."""

from __future__ import annotations

from permdiff.models.base import Frozen
from permdiff.models.decision import EFFECT_ORDER, Decision, Effect, ErrorKind
from permdiff.models.report import Counts, Report, ReportHeader
from permdiff.models.toolcall import (
    Agent,
    Principal,
    Recorded,
    Resource,
    Source,
    Tool,
    ToolCall,
)
from permdiff.models.transition import CHANGE_CLASSES, Transition, TransitionClass, classify

__all__ = [
    "CHANGE_CLASSES",
    "EFFECT_ORDER",
    "Agent",
    "Counts",
    "Decision",
    "Effect",
    "ErrorKind",
    "Frozen",
    "Principal",
    "Recorded",
    "Report",
    "ReportHeader",
    "Resource",
    "Source",
    "Tool",
    "ToolCall",
    "Transition",
    "TransitionClass",
    "classify",
]
