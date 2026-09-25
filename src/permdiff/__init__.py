"""permdiff: terraform plan for AI agent permission changes.

Replays recorded agent tool calls against an authorization policy at two git
refs and reports which decisions change.
"""

from __future__ import annotations

from permdiff.models import Decision, Effect, ErrorKind, ToolCall

__version__ = "0.1.0.dev0"

__all__ = ["Decision", "Effect", "ErrorKind", "ToolCall", "__version__"]
