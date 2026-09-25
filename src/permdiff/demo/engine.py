"""Rule-table engine for the bundled demo (``--engine python`` variant of FR-24).

Each policy directory holds a ``rules.py`` defining ``RULES`` (a tuple of
``Rule``) and ``DEFAULT``. The first matching rule wins. It is deliberately
tiny: the demo shows what permdiff reports, not how to write policy.
"""

from __future__ import annotations

import fnmatch
import importlib.util
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from permdiff.models import Decision, ErrorKind, ToolCall

RULES_FILE = "rules.py"
ENGINE_NAME = "demo"


@dataclass(frozen=True)
class Rule:
    tool: str
    """Tool name or glob (``fnmatch``)."""
    effect: str
    reason: str = ""
    when: Callable[[ToolCall], bool] | None = None
    """Extra condition; the rule is skipped when it returns False."""
    requires: tuple[str, ...] = field(default_factory=tuple)
    """Dotted paths that must resolve on the call, else ``error/missing_context``."""


@dataclass(frozen=True)
class RuleTable:
    rules: tuple[Rule, ...]
    default: str
    source: str


def lookup(call: ToolCall, path: str) -> Any:
    """Resolve ``principal.attrs.department`` style paths; ``None`` when absent."""
    node: Any = call
    for part in path.split("."):
        node = node.get(part) if isinstance(node, Mapping) else getattr(node, part, None)
        if node is None:
            return None
    return node


@cache
def load_rules(policy_dir: Path) -> RuleTable:
    rules_path = policy_dir / RULES_FILE
    spec = importlib.util.spec_from_file_location(
        f"permdiff_demo_rules_{id(policy_dir)}", rules_path
    )
    if spec is None or spec.loader is None:
        msg = f"cannot load {rules_path}"
        raise FileNotFoundError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return RuleTable(rules=tuple(module.RULES), default=str(module.DEFAULT), source=RULES_FILE)


def evaluate(call: ToolCall, policy_dir: Path) -> Decision | str:
    """Callable with the ``python:`` engine signature."""
    table = load_rules(policy_dir)
    for rule in table.rules:
        if not fnmatch.fnmatchcase(call.tool.name, rule.tool):
            continue
        for path in rule.requires:
            if lookup(call, path) is None:
                return Decision.error(call.id, ErrorKind.MISSING_CONTEXT, path, engine=ENGINE_NAME)
        if rule.when is not None and not rule.when(call):
            continue
        return Decision.from_effect(
            rule.effect,
            call_id=call.id,
            engine=ENGINE_NAME,
            reasons=(rule.reason,) if rule.reason else (),
            determining=(f"{table.source}:{rule.tool}={rule.effect}",),
        )
    return table.default
