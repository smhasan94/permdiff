"""Reporters and gates. Every reporter receives an already-redacted Report."""

from __future__ import annotations

from permdiff.report.exit_codes import (
    EXIT_GATE,
    EXIT_OK,
    EXIT_TOOL_ERROR,
    FailOn,
    gate,
    gate_reason,
)
from permdiff.report.terminal import render_terminal

__all__ = [
    "EXIT_GATE",
    "EXIT_OK",
    "EXIT_TOOL_ERROR",
    "FailOn",
    "gate",
    "gate_reason",
    "render_terminal",
]
