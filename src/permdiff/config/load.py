"""Config resolution: flags > environment > ``permdiff.toml`` > defaults (AC-23.1, AC-23.3)."""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import ValidationError

from permdiff.config.model import CONFIG_FILENAME, ENV_PREFIX, Config
from permdiff.errors import ConfigError

log = logging.getLogger(__name__)

ENV_CONFIG = "PERMDIFF_CONFIG"
Overrides = Mapping[str, Mapping[str, Any]]
"""``{section: {key: value}}``; only keys actually given by the caller."""

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def find_config(start: Path, *, stop_at: Path | None = None) -> Path | None:
    """Nearest ``permdiff.toml`` walking up from ``start``; stops after ``stop_at`` (repo root)."""
    current = start.resolve()
    stop = stop_at.resolve() if stop_at is not None else None
    for directory in (current, *current.parents):
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if stop is not None and directory == stop:
            break
    return None


def read_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        msg = f"cannot read config {path}: {exc.strerror or exc}"
        raise ConfigError(msg) from exc
    except tomllib.TOMLDecodeError as exc:
        msg = f"{path}: invalid TOML: {exc}"
        raise ConfigError(msg) from exc
    _reject_unknown(data, source=str(path))
    return data


def _reject_unknown(data: Mapping[str, Any], *, source: str) -> None:
    sections = Config.model_fields
    for section, body in data.items():
        if section not in sections:
            msg = f"{source}: unknown section [{section}]; known: {', '.join(sections)}"
            raise ConfigError(msg)
        if not isinstance(body, Mapping):
            msg = f"{source}: [{section}] must be a table"
            raise ConfigError(msg)
        section_model = sections[section].annotation
        known = getattr(section_model, "model_fields", {})
        for key in body:
            if key not in known:
                msg = f"{source}: unknown key {section}.{key}; known: {', '.join(known)}"
                raise ConfigError(msg)


def _coerce_env(section: str, key: str, raw: str) -> Any:
    """Parse an environment string according to the field's declared type."""
    field = Config.model_fields[section].annotation.model_fields[key]  # type: ignore[union-attr]
    annotation = field.annotation
    origin = get_origin(annotation)
    if annotation is bool:
        lowered = raw.strip().lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        msg = f"{ENV_PREFIX}_{section.upper()}_{key.upper()}: expected true/false, got {raw!r}"
        raise ConfigError(msg)
    if annotation is int:
        try:
            return int(raw)
        except ValueError as exc:
            msg = f"{ENV_PREFIX}_{section.upper()}_{key.upper()}: expected an integer, got {raw!r}"
            raise ConfigError(msg) from exc
    if origin is tuple:
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    if origin is not None and type(None) in get_args(annotation) and raw == "":
        return None
    return raw


def env_overrides(env: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    """``PERMDIFF_<SECTION>_<KEY>`` variables as an overrides mapping."""
    result: dict[str, dict[str, Any]] = {}
    for section, info in Config.model_fields.items():
        keys = getattr(info.annotation, "model_fields", {})
        for key in keys:
            name = f"{ENV_PREFIX}_{section.upper()}_{key.upper()}"
            if name in env:
                result.setdefault(section, {})[key] = _coerce_env(section, key, env[name])
    return result


def _merge(*layers: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for layer in layers:
        for section, body in layer.items():
            merged.setdefault(section, {}).update({k: v for k, v in body.items() if v is not None})
    return merged


def load_config(
    start: Path,
    *,
    env: Mapping[str, str],
    overrides: Overrides | None = None,
    explicit: Path | None = None,
    stop_at: Path | None = None,
) -> Config:
    """Resolve the effective configuration.

    ``explicit`` beats ``PERMDIFF_CONFIG`` beats discovery from ``start``.
    """
    path = explicit or (Path(env[ENV_CONFIG]) if env.get(ENV_CONFIG) else None)
    if path is not None and not path.is_file():
        msg = f"config file not found: {path} (from --config or {ENV_CONFIG})"
        raise ConfigError(msg)
    if path is None:
        path = find_config(start, stop_at=stop_at)
    file_layer = read_file(path) if path is not None else {}
    if path is not None:
        log.info("using config %s", path)
    merged = _merge(file_layer, env_overrides(env), overrides or {})
    try:
        return Config.model_validate(merged)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        msg = f"invalid configuration value for {loc}: {first['msg']}"
        raise ConfigError(msg) from exc
