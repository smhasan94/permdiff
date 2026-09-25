"""Root click group. Maps PermdiffError to exit codes in one place."""

from __future__ import annotations

import logging
import sys

import click

from permdiff import __version__
from permdiff.errors import PermdiffError

PACKAGE_LOGGER = "permdiff"


def _configure_logging(verbose: bool, debug: bool) -> None:
    """Set the package logger level; attach a stderr handler if none exists."""
    level = logging.DEBUG if debug else logging.INFO if verbose else logging.WARNING
    logging.getLogger(PACKAGE_LOGGER).setLevel(level)
    if not logging.getLogger().handlers:
        logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
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


def main() -> int:
    """Entry point that converts PermdiffError into exit codes."""
    try:
        result = cli.main(standalone_mode=False)
    except PermdiffError as exc:
        click.echo(f"error: {exc}", err=True)
        return exc.exit_code
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code
    # In non-standalone mode click returns ``Exit.exit_code`` (e.g. from
    # ``--version``) instead of raising; any other return value means success.
    return result if isinstance(result, int) else 0
