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
from permdiff.report.json_ import JsonReport, render_json
from permdiff.report.markdown import MARKER, render_markdown
from permdiff.report.sarif import render_sarif
from permdiff.report.terminal import render_terminal
from permdiff.report.view import ReportView, build_view

__all__ = [
    "EXIT_GATE",
    "EXIT_OK",
    "EXIT_TOOL_ERROR",
    "MARKER",
    "FailOn",
    "JsonReport",
    "ReportView",
    "build_view",
    "gate",
    "gate_reason",
    "render_json",
    "render_markdown",
    "render_sarif",
    "render_terminal",
]
