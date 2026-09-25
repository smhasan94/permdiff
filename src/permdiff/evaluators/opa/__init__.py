"""OPA evaluator (``--engine opa``)."""

from __future__ import annotations

from permdiff.evaluators.opa.binary import OPA_VERSION, resolve_binary
from permdiff.evaluators.opa.evaluator import DEFAULT_DECISION, OpaEvaluator, OpaOptions
from permdiff.evaluators.opa.mapping import UndefinedPolicy

__all__ = [
    "DEFAULT_DECISION",
    "OPA_VERSION",
    "OpaEvaluator",
    "OpaOptions",
    "UndefinedPolicy",
    "resolve_binary",
]
