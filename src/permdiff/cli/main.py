"""Root click group. Maps PermdiffError to exit codes in one place."""

from __future__ import annotations

import logging
import sys
from typing import Any

import click

from permdiff import __version__
from permdiff.cli.check import check_cmd
from permdiff.cli.demo import demo_cmd
from permdiff.cli.diff import diff_cmd
from permdiff.cli.schema import schema_cmd
from permdiff.cli.setup import setup_group
from permdiff.errors import EXIT_GATE, EXIT_TOOL_ERROR, PermdiffError

PACKAGE_LOGGER = "permdiff"


class CliError(click.ClickException):
    """A PermdiffError surfaced through click with an ``error:`` prefix. Exit 1."""

    exit_code = EXIT_TOOL_ERROR

    def show(self, file: Any = None) -> None:
        click.echo(f"error: {self.message}", err=True)


class CliGateError(CliError):
    """A GateFailedError surfaced through click. Exit 2."""

    exit_code = EXIT_GATE


class PermdiffGroup(click.Group):
    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except PermdiffError as exc:
            wrapper = CliGateError if exc.exit_code == EXIT_GATE else CliError
            raise wrapper(str(exc)) from exc


def _configure_logging(verbose: bool, debug: bool) -> None:
    """Set the package logger level; attach a stderr handler if none exists."""
    level = logging.DEBUG if debug else logging.INFO if verbose else logging.WARNING
    logging.getLogger(PACKAGE_LOGGER).setLevel(level)
    if not logging.getLogger().handlers:
        logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)


@click.group(cls=PermdiffGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="permdiff")
@click.option("--verbose", is_flag=True, help="Print engine commands and timings.")
@click.option("--debug", is_flag=True, help="Keep temp dirs and print their paths.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, debug: bool) -> None:
    """terraform plan for AI agent permission changes."""
    _configure_logging(verbose, debug)
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["debug"] = debug


cli.add_command(schema_cmd)
cli.add_command(diff_cmd)
cli.add_command(check_cmd)
cli.add_command(demo_cmd)
cli.add_command(setup_group)
