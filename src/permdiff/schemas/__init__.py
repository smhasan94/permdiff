"""JSON Schema for the canonical models (AC-1.3).

Checked-in ``*.json`` files next to this module ship in the wheel; a test
asserts they match the generated schema. Regenerate with
``permdiff schema <name> > src/permdiff/schemas/<name>.json``.
"""

from __future__ import annotations

import json
from typing import Any, Final

from pydantic import BaseModel

from permdiff.models import Decision, ToolCall

SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID_BASE: Final = "https://permdiff.dev/schemas/v1"

_MODELS: Final[dict[str, type[BaseModel]]] = {
    "toolcall": ToolCall,
    "decision": Decision,
}

SCHEMA_NAMES: Final[tuple[str, ...]] = tuple(_MODELS)


def json_schema(name: str) -> dict[str, Any]:
    """Generated JSON Schema (draft 2020-12) for ``toolcall`` or ``decision``."""
    try:
        model = _MODELS[name]
    except KeyError:
        msg = f"unknown schema {name!r}; expected one of {', '.join(SCHEMA_NAMES)}"
        raise KeyError(msg) from None
    schema = model.model_json_schema(mode="validation")
    return {
        "$schema": SCHEMA_DIALECT,
        "$id": f"{SCHEMA_ID_BASE}/{name}.schema.json",
        **schema,
    }


def schema_text(name: str) -> str:
    """Deterministic pretty JSON, newline-terminated, byte-identical to the checked-in file."""
    return json.dumps(json_schema(name), indent=2, sort_keys=True) + "\n"
