"""Resolve ``--engine`` specs: ``python:mod:fn`` or a ``permdiff.evaluators`` entry point."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable, Iterable
from importlib.metadata import EntryPoint, entry_points
from typing import Any

from pydantic import ValidationError

from permdiff.errors import EngineError
from permdiff.evaluators.base import Evaluator
from permdiff.evaluators.python_callable import PythonCallableEvaluator

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "permdiff.evaluators"
PYTHON_PREFIX = "python:"
PYTHON_FORM = "python:module.path:callable"


def _entry_points() -> Iterable[EntryPoint]:
    return entry_points(group=ENTRY_POINT_GROUP)


def _make_opa(**options: Any) -> Evaluator:
    from permdiff.evaluators.opa import (  # noqa: PLC0415  # keep CLI start fast
        OpaEvaluator,
        OpaOptions,
    )

    try:
        return OpaEvaluator(OpaOptions(**options))
    except (ValidationError, ValueError) as exc:
        msg = f"invalid options for --engine opa: {exc}"
        raise EngineError(msg) from exc


_BUILTIN: dict[str, Callable[..., Evaluator]] = {"opa": _make_opa}


def names() -> tuple[str, ...]:
    """Built-in engine names plus ``permdiff.evaluators`` entry points."""
    return tuple(sorted(set(_BUILTIN) | {ep.name for ep in _entry_points()}))


def resolve(engine_spec: str, **options: Any) -> Evaluator:
    """Build the evaluator for ``engine_spec``; ``options`` go to the engine's factory."""
    if engine_spec.startswith(PYTHON_PREFIX):
        if options:
            log.debug("ignoring engine options for %s: %s", engine_spec, sorted(options))
        return _resolve_python(engine_spec)
    if factory := _BUILTIN.get(engine_spec):
        return factory(**options)
    for ep in _entry_points():
        if ep.name == engine_spec:
            return _load_entry_point(ep, options)
    available = ", ".join(names()) or "none installed"
    msg = (
        f"unknown engine {engine_spec!r} for --engine; available: {available}; "
        f"or use the form {PYTHON_FORM}"
    )
    raise EngineError(msg)


def _resolve_python(spec: str) -> Evaluator:
    module_name, sep, attr = spec.removeprefix(PYTHON_PREFIX).partition(":")
    if not sep or not module_name or not attr:
        msg = f"invalid engine spec {spec!r}; expected {PYTHON_FORM}"
        raise EngineError(msg)
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        msg = f"cannot import module {module_name!r} for --engine {spec}: {exc}"
        raise EngineError(msg) from exc
    fn = getattr(module, attr, None)
    if fn is None:
        msg = f"module {module_name!r} has no attribute {attr!r} for --engine {spec}"
        raise EngineError(msg)
    if not callable(fn):
        msg = f"{module_name}.{attr} is not callable for --engine {spec}"
        raise EngineError(msg)
    log.info("--engine %s runs arbitrary Python from the current environment", spec)
    return PythonCallableEvaluator(spec, fn)


def _load_entry_point(ep: EntryPoint, options: dict[str, Any]) -> Evaluator:
    try:
        factory = ep.load()
        evaluator = factory(**options)
    except Exception as exc:
        msg = f"engine entry point {ep.name!r} ({ep.value}) failed to load: {exc}"
        raise EngineError(msg) from exc
    if not isinstance(evaluator, Evaluator):
        msg = f"engine entry point {ep.name!r} did not return an Evaluator"
        raise EngineError(msg)
    return evaluator
