"""``permdiff schema``: print the JSON Schema of a canonical model."""

from __future__ import annotations

import click

from permdiff import schemas


@click.command("schema")
@click.argument("name", type=click.Choice(schemas.SCHEMA_NAMES, case_sensitive=False))
def schema_cmd(name: str) -> None:
    """Print the JSON Schema for NAME (toolcall or decision)."""
    click.echo(schemas.schema_text(name.lower()), nl=False)
