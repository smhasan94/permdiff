from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from permdiff import demo
from permdiff.demo.engine import Rule, evaluate, load_rules, lookup
from permdiff.models import Decision, Effect, ErrorKind, ToolCall


def _call(tool: str, **overrides: Any) -> ToolCall:
    record: dict[str, Any] = {
        "id": "c",
        "timestamp": datetime(2026, 9, 20, tzinfo=UTC).isoformat(),
        "principal": {"id": "p", "attrs": {"team": "ops"}},
        "agent": {"id": "a"},
        "tool": {"name": tool},
        "context": {"env": "prod"},
        **overrides,
    }
    return ToolCall.model_validate(record)


def _write_rules(tmp_path: Path, body: str) -> Path:
    (tmp_path / "rules.py").write_text(
        "from permdiff.demo.engine import Rule\n" + body, encoding="utf-8"
    )
    return tmp_path


def test_lookup_walks_attributes_and_mappings() -> None:
    call = _call("t")

    assert lookup(call, "principal.attrs.team") == "ops"
    assert lookup(call, "principal.attrs.missing") is None
    assert lookup(call, "tool.name") == "t"
    assert lookup(call, "nope.deeper") is None


def test_first_matching_rule_wins_and_glob_matches(tmp_path: Path) -> None:
    policy = _write_rules(
        tmp_path,
        'DEFAULT = "deny"\nRULES = (Rule(tool="github.*", effect="allow", reason="r1"),'
        ' Rule(tool="github.read", effect="deny"),)\n',
    )

    d = evaluate(_call("github.read"), policy)

    assert isinstance(d, Decision)
    assert d.effect is Effect.ALLOW
    assert d.reasons == ("r1",)
    assert d.determining == ("rules.py:github.*=allow",)


def test_default_applies_when_nothing_matches(tmp_path: Path) -> None:
    policy = _write_rules(tmp_path, 'DEFAULT = "require_approval"\nRULES = ()\n')

    assert evaluate(_call("anything"), policy) == "require_approval"


def test_when_condition_skips_the_rule(tmp_path: Path) -> None:
    policy = _write_rules(
        tmp_path,
        'DEFAULT = "deny"\nRULES = (Rule(tool="x", effect="allow",'
        ' when=lambda c: c.context.get("env") != "prod"),)\n',
    )

    assert evaluate(_call("x"), policy) == "deny"
    d = evaluate(_call("x", context={"env": "dev"}), policy)
    assert isinstance(d, Decision)
    assert d.effect is Effect.ALLOW


def test_requires_missing_path_is_missing_context(tmp_path: Path) -> None:
    policy = _write_rules(
        tmp_path,
        'DEFAULT = "deny"\nRULES = (Rule(tool="x", effect="allow",'
        ' requires=("principal.attrs.department",)),)\n',
    )

    d = evaluate(_call("x"), policy)

    assert isinstance(d, Decision)
    assert d.error_kind is ErrorKind.MISSING_CONTEXT
    assert d.reasons == ("principal.attrs.department",)


def test_rules_are_cached_per_directory(tmp_path: Path) -> None:
    policy = _write_rules(tmp_path, 'DEFAULT = "deny"\nRULES = ()\n')

    assert load_rules(policy) is load_rules(policy)


def test_missing_rules_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_rules(tmp_path / "nowhere")


def test_bundled_policies_load_and_differ() -> None:
    base = load_rules(demo.POLICY_BASE)
    head = load_rules(demo.POLICY_HEAD)

    assert base.default == head.default == "deny"
    assert all(isinstance(r, Rule) for r in base.rules + head.rules)
    assert {r.tool for r in base.rules} <= {r.tool for r in head.rules}
    assert base.rules != head.rules
