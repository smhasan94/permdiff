"""OPA evaluator (``--engine opa``)."""

from __future__ import annotations

from permdiff.evaluators.opa.binary import OPA_VERSION, resolve_binary

__all__ = ["OPA_VERSION", "resolve_binary"]
