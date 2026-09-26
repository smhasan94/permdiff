"""Minimal TOML writer for ``permdiff init`` (stdlib has no TOML writer)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from permdiff.config.model import Config

_COMMENTS: dict[str, str] = {
    "policy.engine": "opa | cedar | python:<module>:<callable>",
    "policy.head": "git ref, or WORKTREE for the uncommitted policy",
    "opa.capabilities": "default (no network builtins) | path to a capabilities file",
    "opa.nd_cache": "recorded nd_builtin_cache JSON to replay, or empty",
    "traces.format": (
        "auto | jsonl | custody | otel | claude-code | claude-code-hooks | opa-decision-log"
    ),
    "traces.input_map": "OPA decision logs: target=source pairs for a foreign input shape",
    "traces.since": "window on trace timestamps, e.g. 7d (relative to the newest trace)",
    "report.redact": "safe | none (local only)",
    "report.fail_on": "widen | any-change | cant-evaluate | none",
}


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_literal(v) for v in value) + "]"
    msg = f"cannot write {type(value).__name__} to TOML"
    raise TypeError(msg)


def render_toml(config: Config, *, sections: tuple[str, ...] | None = None) -> str:
    """The config as TOML with every key present, commented where a value needs explanation."""
    data: Mapping[str, Mapping[str, Any]] = config.model_dump(mode="json")
    lines = ["# permdiff configuration. Flags override environment overrides this file.", ""]
    for section, body in data.items():
        if sections is not None and section not in sections:
            continue
        lines.append(f"[{section}]")
        for key, value in body.items():
            comment = _COMMENTS.get(f"{section}.{key}")
            suffix = f"  # {comment}" if comment else ""
            if value is None:  # unset: shown commented out so the key is discoverable
                lines.append(f'# {key} = ""{suffix}')
                continue
            lines.append(f"{key} = {_literal(value)}{suffix}")
        lines.append("")
    return "\n".join(lines)
