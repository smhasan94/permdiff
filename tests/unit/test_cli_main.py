from __future__ import annotations

import logging
from collections.abc import Iterator

import click
import pytest

from permdiff.cli import main as main_module
from permdiff.errors import EXIT_GATE, EXIT_TOOL_ERROR, GateFailedError, PermdiffError


@pytest.fixture
def failing_command(monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setattr("sys.argv", ["permdiff", "boom", "gate"])


def _run(monkeypatch: pytest.MonkeyPatch, kind: str) -> int:
    monkeypatch.setattr("sys.argv", ["permdiff", "boom", kind])
    return main_module.main()


def test_main_maps_gate_failure_to_exit_two(
    failing_command: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(monkeypatch, "gate") == EXIT_GATE
    assert "error: widening found" in capsys.readouterr().err


def test_main_maps_permdiff_error_to_exit_one(
    failing_command: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(monkeypatch, "tool") == EXIT_TOOL_ERROR
    assert "bad ref: nope" in capsys.readouterr().err


def test_main_shows_click_exceptions(
    failing_command: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(monkeypatch, "click") == 1
    assert "usage problem" in capsys.readouterr().err


def test_main_propagates_click_exit_code(
    failing_command: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _run(monkeypatch, "exit") == 5


def test_main_returns_zero_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["permdiff", "--version"])
    assert main_module.main() == 0


@pytest.fixture
def restore_package_logger() -> Iterator[logging.Logger]:
    logger = logging.getLogger(main_module.PACKAGE_LOGGER)
    previous = logger.level
    yield logger
    logger.setLevel(previous)


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ([], logging.WARNING),
        (["--verbose"], logging.INFO),
        (["--debug"], logging.DEBUG),
    ],
)
def test_global_flags_set_package_log_level(
    failing_command: None,
    restore_package_logger: logging.Logger,
    monkeypatch: pytest.MonkeyPatch,
    flags: list[str],
    expected: int,
) -> None:
    monkeypatch.setattr("sys.argv", ["permdiff", *flags, "boom", "ok"])
    assert main_module.main() == 0
    assert restore_package_logger.level == expected


def test_version_flag_exits_before_group_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["permdiff", "--debug", "--version"])
    assert main_module.main() == 0
