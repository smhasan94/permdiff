"""permdiff: terraform plan for AI agent permission changes.

Replays recorded agent tool calls against an authorization policy at two git
refs and reports which decisions change.
"""

from __future__ import annotations

from permdiff.api import diff, load_traces
from permdiff.evaluators import Evaluator
from permdiff.models import Decision, Effect, ErrorKind, Report, ToolCall, Transition

__version__ = "0.1.0"

__all__ = [
    "Decision",
    "Effect",
    "ErrorKind",
    "Evaluator",
    "Report",
    "ToolCall",
    "Transition",
    "__version__",
    "diff",
    "load_traces",
]
