"""Static rule-name → ``file:row`` index for OPA policies (FR-L7).

Built once per ref from ``opa parse -f json --json-include locations`` over every
``.rego`` file in the policy directory (verified with OPA 1.21.0 on 2026-09-26). A label
is a string literal under ``rule`` or ``rules`` in a rule head value, which is what
permdiff policies return in their decision objects; rule names and ``package.rule`` paths
are indexed too. The first definition wins.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from permdiff import _proc
from permdiff.models import Decision, Frozen

log = logging.getLogger(__name__)

LABEL_KEYS = ("rule", "rules")


class RuleIndex(Frozen):
    by_label: Mapping[str, str]
    by_name: Mapping[str, str]

    def lookup(self, label: str) -> str | None:
        return self.by_label.get(label) or self.by_name.get(label)


EMPTY_INDEX = RuleIndex(by_label={}, by_name={})


def _strings(term: Any) -> tuple[str, ...]:
    if not isinstance(term, Mapping):
        return ()
    if term.get("type") == "string" and isinstance(term.get("value"), str):
        return (term["value"],)
    if term.get("type") == "array" and isinstance(term.get("value"), list):
        return tuple(s for item in term["value"] for s in _strings(item))
    return ()


def labels_of_head(value: Any) -> tuple[str, ...]:
    """String literals under ``rule`` / ``rules`` in an object-valued rule head."""
    if not isinstance(value, Mapping) or value.get("type") != "object":
        return ()
    labels: list[str] = []
    for pair in value.get("value") or []:
        if not isinstance(pair, list) or len(pair) != 2:
            continue
        key, term = pair
        if isinstance(key, Mapping) and key.get("value") in LABEL_KEYS:
            labels.extend(_strings(term))
    return tuple(labels)


def _package_path(document: Mapping[str, Any]) -> str:
    package = document.get("package")
    parts = package.get("path") if isinstance(package, Mapping) else None
    names = [p.get("value") for p in parts or [] if isinstance(p, Mapping)]
    return ".".join(str(n) for n in names[1:])  # drop the leading "data" var


def _rule_name(rule: Mapping[str, Any]) -> str | None:
    head = rule.get("head")
    if not isinstance(head, Mapping):
        return None
    name = head.get("name")
    if isinstance(name, str) and name:
        return name
    ref = head.get("ref")
    if isinstance(ref, list) and ref and isinstance(ref[0], Mapping):
        value = ref[0].get("value")
        return str(value) if value else None
    return None


def _index_document(
    document: Mapping[str, Any], location: str, by_label: dict[str, str], by_name: dict[str, str]
) -> None:
    package = _package_path(document)
    for rule in document.get("rules") or []:
        if not isinstance(rule, Mapping):
            continue
        loc = rule.get("location")
        row = loc.get("row") if isinstance(loc, Mapping) else None
        if not isinstance(row, int):
            continue
        where = f"{location}:{row}"
        raw_head = rule.get("head")
        head: Mapping[str, Any] = raw_head if isinstance(raw_head, Mapping) else {}
        # complete rules: head.value; partial sets (`x contains {...}`): head.key
        for label in (*labels_of_head(head.get("value")), *labels_of_head(head.get("key"))):
            by_label.setdefault(label, where)
        name = _rule_name(rule)
        if name:
            by_name.setdefault(name, where)
            if package:
                by_name.setdefault(f"{package}.{name}", where)
                by_name.setdefault(f"data.{package}.{name}", where)


def build(binary: Path, policy_dir: Path, *, extra_flags: Sequence[str | Path] = ()) -> RuleIndex:
    """Parse every ``.rego`` under ``policy_dir``; a file that fails to parse is skipped."""
    by_label: dict[str, str] = {}
    by_name: dict[str, str] = {}
    for path in sorted(policy_dir.rglob("*.rego")):
        argv: list[str | Path] = [binary, "parse", "-f", "json", "--json-include", "locations"]
        argv += [*extra_flags, path]
        result = _proc.run(argv)
        if not result.ok:
            log.warning("rule index: cannot parse %s: %s", path, (result.stderr or "").strip())
            continue
        try:
            document = json.loads(result.stdout)
        except ValueError:
            log.warning("rule index: unexpected output from opa parse for %s", path)
            continue
        if isinstance(document, Mapping):
            _index_document(document, path.relative_to(policy_dir).as_posix(), by_label, by_name)
    return RuleIndex(by_label=by_label, by_name=by_name)


def attach(decision: Decision, index: RuleIndex) -> Decision:
    """The decision with ``locations`` for every determining label the index knows."""
    if not decision.determining:
        return decision
    found = tuple(loc for label in decision.determining if (loc := index.lookup(label)))
    if not found:
        return decision
    return decision.model_copy(update={"locations": found})
