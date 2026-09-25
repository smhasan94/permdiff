"""``permdiff diff``: the core command (FR-27)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import click

from permdiff import _proc, api
from permdiff.cli._render import emit_and_exit
from permdiff.cli.settings import (
    engine_options,
    load_filtered_traces,
    output_flags,
    output_options,
    resolve_config,
    selection_flags,
)
from permdiff.errors import ConfigError, ProcError


def actor() -> str:
    """Who approved a widening: ``GITHUB_ACTOR``, else git's user.name, else ``unknown``."""
    if name := os.environ.get("GITHUB_ACTOR"):
        return name
    try:
        result = _proc.run(["git", "config", "user.name"])
    except ProcError:
        return "unknown"
    return result.stdout.strip() or "unknown"


REPO_ID_ENV = "GITHUB_REPOSITORY_ID"


def parse_salt(salt_hex: str | None) -> bytes | None:
    """``--salt HEX``; in GitHub Actions a repository-scoped default keeps hashes stable."""
    if salt_hex is None:
        repo_id = os.environ.get(REPO_ID_ENV)
        if repo_id:
            return hashlib.sha256(f"permdiff:{repo_id}".encode()).digest()[:16]
        return None
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError as exc:
        msg = f"--salt must be hex, got {salt_hex!r}"
        raise ConfigError(msg) from exc
    if not salt:
        msg = "--salt must not be empty"
        raise ConfigError(msg)
    return salt


@click.command("diff")
@selection_flags
@click.option("--allow-widening", metavar="REASON", help="Exit 0 on widening; record REASON.")
@click.option("--verify-deterministic", is_flag=True, help="Evaluate twice; flag differences.")
@output_flags
@click.pass_context
def diff_cmd(ctx: click.Context, /, **kwargs: Any) -> None:
    """Replay traces against the policy at two refs and report decision changes."""
    repo: Path = kwargs.pop("repo")
    opa_bin: Path | None = kwargs.pop("opa_bin")
    config = resolve_config(ctx, repo, kwargs)
    opts = output_options(config, kwargs)
    salt = parse_salt(kwargs.pop("salt_hex"))
    allow_widening = kwargs.pop("allow_widening")
    imported, selected = load_filtered_traces(config, kwargs)
    options = engine_options(config)
    if opa_bin is not None:
        options["opa_bin"] = opa_bin
    report = api.diff(
        traces=selected.calls,
        window=selected.window,
        base=config.policy.base,
        head=config.policy.head,
        policy=config.policy.path,
        engine=config.policy.engine,
        repo=repo,
        engine_options=options,
        salt=salt,
        verify_deterministic=kwargs.pop("verify_deterministic"),
        keep_temp=bool(ctx.obj and ctx.obj.get("debug")),
        import_stats=imported.stats,
        filtered=selected.filtered,
        allow_widening=(allow_widening, actor()) if allow_widening else None,
    )
    emit_and_exit(ctx, report, opts)
