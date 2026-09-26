"""Importer lookup: built-ins first, then ``permdiff.importers`` entry points."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Iterable, Mapping
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Any

from permdiff.errors import TraceImportError
from permdiff.importers.base import Importer
from permdiff.importers.claude_code import ClaudeCodeHooksImporter, ClaudeCodeImporter
from permdiff.importers.custody import CustodyImporter
from permdiff.importers.jsonl import JsonlImporter
from permdiff.importers.opa_log import OpaDecisionLogImporter
from permdiff.importers.otel import OtelImporter

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "permdiff.importers"
_SNIFF_BYTES = 8192

_BUILTIN: tuple[Callable[..., Importer], ...] = (
    JsonlImporter,
    CustodyImporter,
    OtelImporter,
    ClaudeCodeHooksImporter,
    ClaudeCodeImporter,
    OpaDecisionLogImporter,
)
"""Detection order: permdiff JSONL, Custody, OTel, Claude Code hooks and transcripts, OPA logs."""
_ALIASES: dict[str, str] = {"permdiff": "jsonl"}


def _entry_points() -> Iterable[EntryPoint]:
    return entry_points(group=ENTRY_POINT_GROUP)


def _load_external() -> list[Importer]:
    loaded: list[Importer] = []
    for ep in _entry_points():
        try:
            factory = ep.load()
            importer = factory()
        except Exception as exc:  # a broken plugin must not break built-ins
            log.warning("ignoring importer entry point %r: %s", ep.name, exc)
            continue
        if not isinstance(importer, Importer):
            log.warning("ignoring importer entry point %r: not an Importer", ep.name)
            continue
        loaded.append(importer)
    return loaded


def _accepted(factory: Callable[..., Importer], options: Mapping[str, Any]) -> dict[str, Any]:
    """The subset of ``options`` the factory's signature names (each importer takes its own)."""
    try:
        params = inspect.signature(factory).parameters
    except (TypeError, ValueError):
        return {}
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return dict(options)
    return {k: v for k, v in options.items() if k in params}


def _builtins(**options: Any) -> list[Importer]:
    """Instantiate built-ins; each receives only the options its constructor accepts."""
    return [factory(**_accepted(factory, options)) for factory in _BUILTIN]


def all_importers(**options: Any) -> tuple[Importer, ...]:
    """Built-ins, then external, with built-in names taking precedence on collision."""
    builtins = _builtins(**options)
    taken = {i.name for i in builtins}
    external = [i for i in _load_external() if i.name not in taken]
    return (*builtins, *external)


def names() -> tuple[str, ...]:
    return tuple(i.name for i in all_importers())


def get(name: str, **options: Any) -> Importer:
    """Importer by name (``--from``). Unknown names list what is available."""
    wanted = _ALIASES.get(name, name)
    for importer in all_importers(**options):
        if importer.name == wanted:
            return importer
    msg = f"unknown importer {name!r} for --from; available: {', '.join(names())}"
    raise TraceImportError(msg)


def _head(path: Path) -> bytes:
    try:
        with path.open("rb") as fh:
            return fh.read(_SNIFF_BYTES)
    except OSError as exc:
        msg = f"cannot read {path}: {exc.strerror or exc}"
        raise TraceImportError(msg) from exc


def detect(path: Path, **options: Any) -> Importer:
    """First importer whose ``detect`` accepts the file head (``--from auto``)."""
    head = _head(path)
    for importer in all_importers(**options):
        if importer.detect(head):
            log.info("detected format %s for %s", importer.name, path)
            return importer
    msg = f"could not detect the trace format of {path}; pass --from {'|'.join(names())}"
    raise TraceImportError(msg)


def get_for(path: Path, name: str, **options: Any) -> Importer:
    """``--from NAME`` for ``path``: an error when the file clearly is another format (AC-5.2)."""
    importer = get(name, **options)
    head = _head(path)
    if importer.detect(head):
        return importer
    for other in all_importers(**options):
        if other.name != importer.name and other.detect(head):
            msg = (
                f"--from {name}: {path} looks like {other.name} traces, not {importer.name}; "
                f"pass --from {other.name} or --from auto"
            )
            raise TraceImportError(msg)
    return importer
