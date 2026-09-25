"""``permdiff setup opa``: prefetch the pinned engine binary (AC-10.1)."""

from __future__ import annotations

from pathlib import Path

import click

from permdiff.evaluators.opa import binary


@click.group("setup")
def setup_group() -> None:
    """Prefetch engine binaries."""


@setup_group.command("opa")
@click.option("--version", "version", default=binary.OPA_VERSION, show_default=True)
@click.option("--force", is_flag=True, help="Re-download even if already cached.")
def setup_opa(version: str, force: bool) -> None:
    """Download opa into the user cache and verify its checksum."""
    target: Path = binary.cached_path(version)
    if target.is_file() and not force:
        click.echo(f"opa {version} already installed at {target}")
        return
    path = binary.download(version, target.parent)
    click.echo(f"opa {version} installed at {path}")
