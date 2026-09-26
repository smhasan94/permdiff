"""``--input-map``: build a ``ToolCall`` payload from a foreign OPA decision-log ``input``.

``target=source`` pairs. ``target`` is a dotted ``ToolCall`` path; ``source`` is a dotted
path into the event's ``input``, ``event.<path>`` into the event itself, or
``const:<text>``. With a map, ``id`` defaults to the event's ``decision_id`` and
``timestamp`` to the event's ``timestamp``. Design recorded in decisions.md 2026-09-26.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from permdiff.errors import ConfigError
from permdiff.models import Frozen

CONST_PREFIX = "const:"
EVENT_PREFIX = "event."
FIXED_TARGETS = frozenset(
    {
        "id",
        "timestamp",
        "principal.id",
        "principal.type",
        "agent.id",
        "agent.version",
        "tool.name",
        "tool.server",
        "tool.type",
        "arguments",
        "resource.type",
        "resource.id",
    }
)
PREFIX_TARGETS = ("principal.attrs.", "agent.attrs.", "arguments.", "resource.attrs.", "context.")
REQUIRED_TARGETS = ("principal.id", "agent.id", "tool.name")
DEFAULT_SOURCES = (("id", "event.decision_id"), ("timestamp", "event.timestamp"))


class InputMap(Frozen):
    pairs: tuple[tuple[str, str], ...]

    @property
    def targets(self) -> tuple[str, ...]:
        return tuple(target for target, _ in self.pairs)


def _valid_target(target: str) -> bool:
    if target in FIXED_TARGETS:
        return True
    return any(target.startswith(prefix) and len(target) > len(prefix) for prefix in PREFIX_TARGETS)


def parse_input_map(specs: Iterable[str]) -> InputMap:
    """``target=source`` pairs, comma-separated inside one spec allowed; errors name the pair."""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for spec in specs:
        for item in spec.split(","):
            pair = item.strip()
            if not pair:
                continue
            target, sep, source = pair.partition("=")
            target, source = target.strip(), source.strip()
            if not sep or not target or not source:
                msg = f"--input-map {pair!r}: expected target=source"
                raise ConfigError(msg)
            if not _valid_target(target):
                msg = f"--input-map {pair!r}: unknown target {target!r}"
                raise ConfigError(msg)
            if target in seen:
                msg = f"--input-map {pair!r}: {target} mapped twice"
                raise ConfigError(msg)
            seen.add(target)
            pairs.append((target, source))
    if "arguments" in seen and any(t.startswith("arguments.") for t in seen):
        msg = (
            "--input-map: map either arguments (whole object) or arguments.<key> entries, not both"
        )
        raise ConfigError(msg)
    return InputMap(pairs=tuple(pairs))


def _walk(node: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(node, Mapping):
            node = node.get(part)
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return None
        if node is None:
            return None
    return node


def resolve_source(source: str, *, input: Any, event: Mapping[str, Any]) -> Any:
    """The value a source names, or ``None`` when absent."""
    if source.startswith(CONST_PREFIX):
        return source[len(CONST_PREFIX) :]
    if source.startswith(EVENT_PREFIX):
        return _walk(event, source[len(EVENT_PREFIX) :])
    return _walk(input, source)


def _place(payload: dict[str, Any], target: str, value: Any) -> None:
    head, _, rest = target.partition(".")
    if not rest:
        payload[head] = value
        return
    child = payload.setdefault(head, {})
    _place(child, rest, value)


def apply(input_map: InputMap, *, input: Any, event: Mapping[str, Any]) -> dict[str, Any]:
    """A nested ``ToolCall`` payload; absent sources leave their targets out."""
    payload: dict[str, Any] = {}
    mapped = set(input_map.targets)
    pairs = [*((t, s) for t, s in DEFAULT_SOURCES if t not in mapped), *input_map.pairs]
    for target, source in pairs:
        value = resolve_source(source, input=input, event=event)
        if value is None:
            continue
        if target == "arguments" and not isinstance(value, Mapping):
            continue
        _place(payload, target, dict(value) if target == "arguments" else value)
    return payload


def missing_required(input_map: InputMap, payload: Mapping[str, Any]) -> tuple[str, str] | None:
    """The first required target the map could not fill, with its source, else ``None``."""
    sources = dict(input_map.pairs)
    for target in REQUIRED_TARGETS:
        if _walk(payload, target) is None:
            return target, sources.get(target, "(unmapped)")
    return None
