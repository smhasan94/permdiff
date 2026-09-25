"""Recorded nondeterministic-builtin values in OPA's ``nd_builtin_cache`` shape (AC-10.7).

Shape (as OPA decision logs emit it): ``{"<builtin>": {"<json array of args>": <value>}}``.
Keys are canonicalized to compact JSON with sorted object keys, which is what
``json.marshal`` inside the shim produces.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from permdiff.errors import EngineError
from permdiff.evaluators.opa.shim import ND_ROOT
from permdiff.models import Frozen


class NdCache(Frozen):
    entries: Mapping[str, Mapping[str, Any]]
    """builtin name → canonical args key → recorded value."""

    @property
    def builtins(self) -> tuple[str, ...]:
        return tuple(sorted(self.entries))


def canonical_key(args: Any) -> str:
    return json.dumps(args, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def load_nd_cache(path: Path) -> NdCache:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"--nd-cache {path}: cannot read: {exc.strerror or exc}"
        raise EngineError(msg) from exc
    except ValueError as exc:
        msg = f"--nd-cache {path}: not valid JSON: {exc}"
        raise EngineError(msg) from exc
    if isinstance(payload, dict) and isinstance(payload.get("nd_builtin_cache"), dict):
        payload = payload["nd_builtin_cache"]  # a whole decision-log event was passed
    if not isinstance(payload, dict):
        msg = f"--nd-cache {path}: expected an object of builtin name → recorded calls"
        raise EngineError(msg)
    entries: dict[str, dict[str, Any]] = {}
    for builtin, table in payload.items():
        if not isinstance(table, dict):
            msg = f"--nd-cache {path}: entry for {builtin!r} must be an object keyed by JSON args"
            raise EngineError(msg)
        canon: dict[str, Any] = {}
        for key, value in table.items():
            try:
                args = json.loads(key)
            except ValueError as exc:
                msg = f"--nd-cache {path}: key {key!r} under {builtin!r} is not JSON"
                raise EngineError(msg) from exc
            if not isinstance(args, list):
                msg = (
                    f"--nd-cache {path}: key {key!r} under {builtin!r} must be a JSON array of args"
                )
                raise EngineError(msg)
            canon[canonical_key(args)] = value
        entries[builtin] = canon
    return NdCache(entries=entries)


def render_nd_data(cache: NdCache) -> bytes:
    return json.dumps({ND_ROOT: cache.entries}, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
