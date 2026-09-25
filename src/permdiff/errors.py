"""Exception hierarchy. Every message names the file, line, ref, or flag involved."""

from __future__ import annotations

EXIT_OK = 0
EXIT_TOOL_ERROR = 1
EXIT_GATE = 2


class PermdiffError(Exception):
    """Base for all permdiff failures. Maps to exit code 1 unless overridden."""

    exit_code: int = EXIT_TOOL_ERROR


class TraceImportError(PermdiffError):
    """A trace file could not be read or a record was invalid."""


class PolicyError(PermdiffError):
    """A policy could not be located, materialized, or loaded."""


class EngineError(PermdiffError):
    """An evaluator could not be resolved, prepared, or run."""


class ConfigError(PermdiffError):
    """Configuration file, environment, or flag problem."""


class ProcError(PermdiffError):
    """A subprocess could not be started."""


class GateFailedError(PermdiffError):
    """The report matched --fail-on. Exit code 2."""

    exit_code = EXIT_GATE
