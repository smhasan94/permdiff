"""Cedar evaluator (``--engine cedar``), available with ``pip install "permdiff[cedar]"``."""

from __future__ import annotations

from typing import Any

from permdiff.errors import EngineError
from permdiff.evaluators.base import Evaluator

INSTALL_HINT = 'the Cedar engine needs the cedarpy extra: pip install "permdiff[cedar]"'


def make_cedar(**options: Any) -> Evaluator:
    """Factory used by the registry; imports cedarpy lazily so the core stays light."""
    try:
        import cedarpy  # noqa: F401, PLC0415  # presence check only
    except ImportError as exc:
        raise EngineError(INSTALL_HINT) from exc
    from permdiff.evaluators.cedar.evaluator import CedarEvaluator, CedarOptions  # noqa: PLC0415

    return CedarEvaluator(CedarOptions(**options))


__all__ = ["INSTALL_HINT", "make_cedar"]
