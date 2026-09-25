from __future__ import annotations

import logging
from collections.abc import Iterator

import click
import pytest
from click.testing import CliRunner

from permdiff.cli import main as main_module
from permdiff.errors import EXIT_GATE, EXIT_TOOL_ERROR, GateFailedError, PermdiffError


@pytest.fixture
def boom_command() -> Iterator[None]:
    """Install a hidden subcommand that raises whatever exception is configured."""

    @click.command("boom")
    @click.argument("kind")
    def boom(kind: str) -> None:
        if kind == "gate":
            raise GateFailedError("widening found")
        if kind == "tool":
            raise PermdiffError("bad ref: nope")
        if kind == "click":
            raise click.ClickException("usage problem")
        if kind == "exit":
            raise click.exceptions.Exit(5)

    main_module.cli.add_command(boom)
    yield
    del main_module.cli.commands["boom"]


def _run(*args: str) -> tuple[int, str, str]:
    result = CliRunner().invoke(main_module.cli, list(args))
    return result.exit_code, result.stdout, result.stderr


def test_gate_failure_maps_to_exit_two(boom_command: None) -> None:
    code, _out, err = _run("boom", "gate")

    assert code == EXIT_GATE
    assert "error: widening found" in err


def test_permdiff_error_maps_to_exit_one(boom_command: None) -> None:
    code, _out, err = _run("boom", "tool")

    assert code == EXIT_TOOL_ERROR
    assert "error: bad ref: nope" in err


def test_click_exceptions_keep_click_formatting(boom_command: None) -> None:
    code, _out, err = _run("boom", "click")

    assert code == 1
    assert "usage problem" in err


def test_explicit_exit_code_propagates(boom_command: None) -> None:
    assert _run("boom", "exit")[0] == 5


def test_version_flag() -> None:
    code, out, _err = _run("--version")

    assert code == 0
    assert "permdiff, version" in out


@pytest.fixture
def restore_package_logger() -> Iterator[logging.Logger]:
    logger = logging.getLogger(main_module.PACKAGE_LOGGER)
    previous = logger.level
    yield logger
    logger.setLevel(previous)


@pytest.mark.parametrize(
    ("flags", "expected"),
    [([], logging.WARNING), (["--verbose"], logging.INFO), (["--debug"], logging.DEBUG)],
)
def test_global_flags_set_package_log_level(
    boom_command: None, restore_package_logger: logging.Logger, flags: list[str], expected: int
) -> None:
    code, _out, _err = _run(*flags, "boom", "ok")

    assert code == 0
    assert restore_package_logger.level == expected
