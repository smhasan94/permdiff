"""``permdiff init``: write ``permdiff.toml`` from flags (AC-23.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from permdiff.cli.settings import overrides_from
from permdiff.config import CONFIG_FILENAME, Config, render_toml
from permdiff.config.load import _merge
from permdiff.errors import ConfigError


@click.command("init")
@click.option("--engine", default=None, help="opa | python:module:callable")
@click.option("--policy", default=None, help="Policy path in the repo.")
@click.option("--base", default=None, help="Base git ref.")
@click.option("--head", default=None, help="Head git ref or WORKTREE.")
@click.option("--traces", "trace_patterns", multiple=True, help="Trace file or glob.")
@click.option("--decision", default=None, help="OPA rule path.")
@click.option(
    "--fail-on", default=None, type=click.Choice(["widen", "any-change", "cant-evaluate", "none"])
)
@click.option(
    "--path",
    "target",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path(CONFIG_FILENAME),
    show_default=True,
)
@click.option("--force", is_flag=True, help="Overwrite an existing file.")
def init_cmd(**kwargs: Any) -> None:
    """Write permdiff.toml with every key and the values given here."""
    target: Path = kwargs.pop("target")
    force: bool = kwargs.pop("force")
    if target.exists() and not force:
        msg = f"{target} already exists; pass --force to overwrite"
        raise ConfigError(msg)
    config = Config.model_validate(_merge(overrides_from(kwargs)))
    target.write_text(render_toml(config), encoding="utf-8")
    click.echo(f"wrote {target}")
