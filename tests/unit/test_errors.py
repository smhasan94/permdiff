from __future__ import annotations

from permdiff.errors import (
    EXIT_GATE,
    EXIT_TOOL_ERROR,
    ConfigError,
    EngineError,
    GateFailedError,
    PermdiffError,
    PolicyError,
    TraceImportError,
)


def test_all_errors_are_permdiff_errors() -> None:
    for cls in (TraceImportError, PolicyError, EngineError, ConfigError, GateFailedError):
        assert issubclass(cls, PermdiffError)


def test_default_exit_code_is_tool_error() -> None:
    assert PermdiffError("x").exit_code == EXIT_TOOL_ERROR


def test_gate_failed_exit_code_is_two() -> None:
    assert GateFailedError("widening").exit_code == EXIT_GATE
