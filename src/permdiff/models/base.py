"""Shared pydantic base: frozen, no extra fields."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    """Immutable model. Update with ``model_copy(update=...)``, never assign."""

    model_config = ConfigDict(frozen=True, extra="forbid")
