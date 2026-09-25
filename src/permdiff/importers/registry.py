"""Importer lookup: built-ins first, then ``permdiff.importers`` entry points."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path

from permdiff.errors import TraceImportError
from permdiff.importers.base import Importer
from permdiff.importers.jsonl import JsonlImporter

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "permdiff.importers"
_SNIFF_BYTES = 8192

_BUILTIN: tuple[Importer, ...] = (JsonlImporter(),)
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


def all_importers() -> tuple[Importer, ...]:
    """Built-ins, then external, with built-in names taking precedence on collision."""
    taken = {i.name for i in _BUILTIN}
    external = [i for i in _load_external() if i.name not in taken]
    return (*_BUILTIN, *external)


def names() -> tuple[str, ...]:
    return tuple(i.name for i in all_importers())


def get(name: str) -> Importer:
    """Importer by name (``--from``). Unknown names list what is available."""
    wanted = _ALIASES.get(name, name)
    for importer in all_importers():
        if importer.name == wanted:
            return importer
    msg = f"unknown importer {name!r} for --from; available: {', '.join(names())}"
    raise TraceImportError(msg)


def detect(path: Path) -> Importer:
    """First importer whose ``detect`` accepts the file head (``--from auto``)."""
    try:
        with path.open("rb") as fh:
            head = fh.read(_SNIFF_BYTES)
    except OSError as exc:
        msg = f"cannot read {path}: {exc.strerror or exc}"
        raise TraceImportError(msg) from exc
    for importer in all_importers():
        if importer.detect(head):
            log.info("detected format %s for %s", importer.name, path)
            return importer
    msg = f"could not detect the trace format of {path}; pass --from {'|'.join(names())}"
    raise TraceImportError(msg)
