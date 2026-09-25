"""SARIF 2.1.0 reporter (FR-21): one rule per transition class, one result per group."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from typing import Any

from permdiff import __version__
from permdiff.models import TransitionClass
from permdiff.report.exit_codes import FailOn
from permdiff.report.grouping import Group
from permdiff.report.view import ReportView

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
TOOL_NAME = "permdiff"
INFORMATION_URI = "https://github.com/smhasan94/permdiff"

_RULES: dict[TransitionClass, tuple[str, str, str]] = {
    # class -> (rule id, level, short description)
    TransitionClass.WIDENING: (
        "permdiff/widening",
        "error",
        "Calls newly allowed or less restricted",
    ),
    TransitionClass.TIGHTENING: (
        "permdiff/tightening",
        "warning",
        "Calls newly denied or more restricted",
    ),
    TransitionClass.CANT_EVALUATE: (
        "permdiff/cant-evaluate",
        "warning",
        "Calls the policy could not evaluate",
    ),
    TransitionClass.ATTRIBUTION_CHANGE: (
        "permdiff/attribution-change",
        "note",
        "Same effect, different determining policy",
    ),
    TransitionClass.UNCHANGED: ("permdiff/unchanged", "note", "Decision unchanged"),
}
_SECURITY_SEVERITY: dict[TransitionClass, str] = {
    TransitionClass.WIDENING: "8.0",
    TransitionClass.TIGHTENING: "3.0",
    TransitionClass.CANT_EVALUATE: "4.0",
    TransitionClass.ATTRIBUTION_CHANGE: "1.0",
    TransitionClass.UNCHANGED: "0.0",
}
_FILE_LINE = re.compile(r"^(?P<file>[^:\s]+\.[A-Za-z0-9]+):(?P<line>[1-9][0-9]*)$")


def _rules() -> list[dict[str, Any]]:
    return [
        {
            "id": rule_id,
            "name": cls.value,
            "shortDescription": {"text": text},
            "defaultConfiguration": {"level": level},
            "properties": {"security-severity": _SECURITY_SEVERITY[cls]},
        }
        for cls, (rule_id, level, text) in _RULES.items()
    ]


def _location(view: ReportView, group: Group) -> dict[str, Any]:
    """The determining head policy file and line when known, else the first policy file, line 1."""
    policy = view.header.policy_path.strip("/") or "."
    uri, line = None, 1
    for t in group.samples:
        for det in t.head.determining:
            m = _FILE_LINE.match(det)
            if m:
                uri, line = m.group("file"), int(m.group("line"))
                break
        if uri:
            break
    if uri is None:
        first = view.header.policy_files[0] if view.header.policy_files else policy
        uri = (
            first
            if first.startswith(policy + "/") or first == policy
            else posixpath.join(policy, first)
        )
    elif not uri.startswith(policy + "/"):
        uri = posixpath.join(policy, uri)
    return {"artifactLocation": {"uri": uri}, "region": {"startLine": line}}


def _logical_locations(group: Group) -> list[dict[str, str]]:
    key = dict(group.key.parts)
    tool = key.get("tool") or (group.samples[0].call.tool.name if group.samples else "")
    principal = key.get("principal") or (
        group.samples[0].call.principal.id if group.samples else ""
    )
    locations = []
    if tool:
        locations.append({"name": tool, "kind": "function"})
    if principal:
        locations.append({"name": principal, "kind": "member"})
    return locations


def _fingerprint(group: Group) -> str:
    material = json.dumps([group.cls.value, list(group.key.parts)], separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _result(view: ReportView, group: Group, rule_index: dict[str, int]) -> dict[str, Any]:
    rule_id, level, _ = _RULES[group.cls]
    reasons = f" Reasons: {'; '.join(group.reasons)}." if group.reasons else ""
    calls = f"{group.count:,} call{'' if group.count == 1 else 's'}"
    text = (
        f"{group.cls.value.replace('_', ' ')}: {group.label} ({calls}, {group.effects}).{reasons}"
    )
    return {
        "ruleId": rule_id,
        "ruleIndex": rule_index[rule_id],
        "level": level,
        "message": {"text": text},
        "locations": [
            {
                "physicalLocation": _location(view, group),
                "logicalLocations": _logical_locations(group),
            }
        ],
        "partialFingerprints": {"primaryLocationLineHash": _fingerprint(group)},
        "properties": {
            "count": group.count,
            "transition": group.cls.value,
            "effects": group.effects,
            "group": dict(group.key.parts),
            "security-severity": _SECURITY_SEVERITY[group.cls],
        },
    }


def render_sarif(view: ReportView, *, exit_code: int, fail_on: FailOn) -> str:
    rules = _rules()
    rule_index = {r["id"]: i for i, r in enumerate(rules)}
    h = view.header
    run: dict[str, Any] = {
        "tool": {
            "driver": {
                "name": TOOL_NAME,
                "version": __version__,
                "informationUri": INFORMATION_URI,
                "rules": rules,
            }
        },
        "results": [_result(view, g, rule_index) for g in view.groups],
        "properties": {
            "base": {"label": h.base_label, "sha": h.base_sha},
            "head": {"label": h.head_label, "sha": h.head_sha, "worktree": h.is_worktree},
            "policy": h.policy_path,
            "engine": h.engine,
            "salt": h.salt,
            "counts": view.counts.model_dump(mode="json"),
            "exitCode": exit_code,
            "failOn": fail_on.value,
            "truncatedGroups": view.truncated_groups,
        },
    }
    if h.head_sha:
        run["versionControlProvenance"] = [
            {"repositoryUri": INFORMATION_URI, "revisionId": h.head_sha}
        ]
    doc = {"$schema": SARIF_SCHEMA, "version": SARIF_VERSION, "runs": [run]}
    return json.dumps(doc, indent=2) + "\n"
