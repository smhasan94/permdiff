"""Load a Cedar policy directory: ``*.cedar``, one ``*.cedarschema``, ``entities.json``."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import cedarpy

from permdiff.errors import EngineError
from permdiff.models import Frozen

ENTITIES_FILE = "entities.json"


class PolicyMeta(Frozen):
    policy_id: str
    """Positional id cedarpy reports in diagnostics (``policy0``, ...)."""
    file: str
    effect: str
    annotations: Mapping[str, str]

    @property
    def label(self) -> str:
        """``@id`` when present, else ``file:policyN``."""
        return self.annotations.get("id") or f"{self.file}:{self.policy_id}"


class PolicyBundle(Frozen):
    policies: str
    schema_text: str | None
    entities: tuple[dict[str, Any], ...]
    meta: Mapping[str, PolicyMeta]
    """Positional policy id → metadata."""
    files: tuple[str, ...]


def _static_policies(text: str) -> dict[str, dict[str, Any]]:
    try:
        parsed = json.loads(cedarpy.policies_to_json_str(text))
    except Exception as exc:  # cedarpy raises plain exceptions with the parser message
        msg = f"cannot parse Cedar policies: {exc}"
        raise EngineError(msg) from exc
    result: dict[str, dict[str, Any]] = dict(parsed.get("staticPolicies", {}))
    return result


def _ordered(policies: Mapping[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    return sorted(policies.items(), key=lambda kv: int(kv[0].removeprefix("policy") or 0))


def load_bundle(policy_dir: Path) -> PolicyBundle:
    """Concatenate policy files in sorted order and remember which file each policy came from."""
    if not policy_dir.is_dir():
        msg = f"cedar policy path {policy_dir} is not a directory"
        raise EngineError(msg)
    files = sorted(p for p in policy_dir.rglob("*.cedar") if p.is_file())
    if not files:
        msg = f"no *.cedar files under {policy_dir}"
        raise EngineError(msg)
    texts: list[str] = []
    meta: dict[str, PolicyMeta] = {}
    offset = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(policy_dir).as_posix()
        try:
            per_file = _static_policies(text)
        except EngineError as exc:
            msg = f"{rel}: {exc}"
            raise EngineError(msg) from exc
        for local_id, body in _ordered(per_file):
            index = offset + int(local_id.removeprefix("policy"))
            policy_id = f"policy{index}"
            meta[policy_id] = PolicyMeta(
                policy_id=policy_id,
                file=rel,
                effect=str(body.get("effect", "")),
                annotations={str(k): str(v) for k, v in (body.get("annotations") or {}).items()},
            )
        offset += len(per_file)
        texts.append(text.rstrip() + "\n")
    schemas = sorted(p for p in policy_dir.rglob("*.cedarschema") if p.is_file())
    if len(schemas) > 1:
        names = ", ".join(p.relative_to(policy_dir).as_posix() for p in schemas)
        msg = f"expected at most one *.cedarschema under {policy_dir}, found: {names}"
        raise EngineError(msg)
    schema_text = schemas[0].read_text(encoding="utf-8") if schemas else None
    entities: tuple[dict[str, Any], ...] = ()
    entities_path = policy_dir / ENTITIES_FILE
    if entities_path.is_file():
        try:
            loaded = json.loads(entities_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            msg = f"{ENTITIES_FILE}: invalid JSON: {exc}"
            raise EngineError(msg) from exc
        if not isinstance(loaded, list):
            msg = f"{ENTITIES_FILE}: expected a JSON array of entities"
            raise EngineError(msg)
        entities = tuple(loaded)
    return PolicyBundle(
        policies="\n".join(texts),
        schema_text=schema_text,
        entities=entities,
        meta=meta,
        files=tuple(p.relative_to(policy_dir).as_posix() for p in files),
    )


def validate(bundle: PolicyBundle) -> str | None:
    """Validation errors against the schema as one message naming files, or ``None``."""
    if bundle.schema_text is None:
        return None
    try:
        result = cedarpy.validate_policies(bundle.policies, bundle.schema_text)
    except Exception as exc:
        return f"schema or policy error: {exc}"
    if result.validation_passed:
        return None
    parts = []
    for err in result.errors:
        meta = bundle.meta.get(err.policy_id)
        where = f"{meta.file} ({meta.label})" if meta else err.policy_id
        parts.append(f"{where}: {err.error}")
    return "; ".join(parts)
