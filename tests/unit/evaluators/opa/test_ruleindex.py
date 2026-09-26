from __future__ import annotations

from pathlib import Path

from permdiff.evaluators.opa.ruleindex import RuleIndex, attach, build, labels_of_head
from permdiff.models import Decision, Effect, ErrorKind

BASIC = Path(__file__).parents[3] / "fixtures" / "opa" / "basic"


def _obj(*pairs: tuple[str, object]) -> dict[str, object]:
    def term(value: object) -> dict[str, object]:
        if isinstance(value, list):
            return {"type": "array", "value": [term(v) for v in value]}
        if isinstance(value, str):
            return {"type": "string", "value": value}
        return {"type": "number", "value": value}

    return {"type": "object", "value": [[term(k), term(v)] for k, v in pairs]}


def test_labels_of_head_reads_rule_and_rules_literals() -> None:
    assert labels_of_head(_obj(("effect", "allow"), ("rule", "read"))) == ("read",)
    assert labels_of_head(_obj(("rules", ["a", "b"]), ("rule", "c"))) == ("a", "b", "c")
    assert labels_of_head(_obj(("effect", "deny"))) == ()
    assert labels_of_head({"type": "string", "value": "deny"}) == ()
    assert labels_of_head(None) == ()
    assert labels_of_head(_obj(("rule", 5))) == ()


def test_build_indexes_labels_names_and_packages(opa_bin: Path) -> None:
    index = build(opa_bin, BASIC)

    assert index.lookup("read") == "agent.rego:7"
    assert index.lookup("refund-large") == "agent.rego:11"
    assert index.lookup("finance") == "agent.rego:11"
    assert index.lookup("default") == "agent.rego:5"
    assert index.lookup("decision") == "agent.rego:5"  # first definition of the rule name
    assert index.lookup("agent.authz.decision") == "agent.rego:5"
    assert index.lookup("data.agent.authz.decision") == "agent.rego:5"
    assert index.lookup("nope") is None


def test_build_tolerates_unparsable_files(opa_bin: Path, tmp_path: Path) -> None:
    (tmp_path / "ok.rego").write_text(
        "package p\nimport rego.v1\n"
        'allow := {"rule": "x"} if true\n'
        'deny contains {"effect": "deny", "rule": "set-rule"} if true\n',
        encoding="utf-8",
    )
    (tmp_path / "broken.rego").write_text("package p\nthis is not rego", encoding="utf-8")
    (tmp_path / "data.json").write_text("{}", encoding="utf-8")

    index = build(opa_bin, tmp_path)

    assert index.lookup("x") == "ok.rego:3"
    assert index.lookup("allow") == "ok.rego:3"
    assert index.lookup("set-rule") == "ok.rego:4"  # partial set: object lives in head.key
    assert index.lookup("deny") == "ok.rego:4"


def test_attach_adds_locations_for_known_labels_only() -> None:
    index = RuleIndex(by_label={"read": "agent.rego:7"}, by_name={"decision": "agent.rego:5"})
    decision = Decision.from_effect(
        Effect.ALLOW, call_id="c1", engine="opa", determining=("read", "mystery", "decision")
    )

    attached = attach(decision, index)

    assert attached.locations == ("agent.rego:7", "agent.rego:5")
    assert attached.determining == decision.determining
    assert attach(decision, RuleIndex(by_label={}, by_name={})).locations == ()
    error = Decision.error("c1", ErrorKind.EVAL_ERROR, "boom", engine="opa")
    assert attach(error, index) == error
