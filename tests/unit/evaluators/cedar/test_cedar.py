from __future__ import annotations

import builtins
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from permdiff.errors import EngineError
from permdiff.evaluators import registry
from permdiff.models import Effect, ErrorKind, ToolCall
from tests.conftest import OPA_FIXTURES

pytest.importorskip("cedarpy")

from permdiff.evaluators.cedar.evaluator import CedarEvaluator
from permdiff.evaluators.cedar.loader import load_bundle, validate
from permdiff.evaluators.cedar.request import (
    MissingTemplateValue,
    build_request,
    missing_name,
    render,
)

FIXTURES = OPA_FIXTURES.parent / "cedar"


def _call(
    call_id: str,
    tool: str,
    *,
    principal: str = "alice",
    args: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    hour: int = 12,
    resource_id: str | None = "r1",
) -> ToolCall:
    return ToolCall.model_validate(
        {
            "id": call_id,
            "timestamp": datetime(2026, 9, 20, hour, tzinfo=UTC).isoformat(),
            "principal": {"id": principal},
            "agent": {"id": "bot"},
            "tool": {"name": tool},
            "arguments": args,
            "resource": {"type": "thing", "id": resource_id},
            "context": context or {},
        }
    )


@pytest.fixture
def cedar() -> CedarEvaluator:
    return CedarEvaluator()


def test_bundle_loads_files_schema_entities_and_annotations() -> None:
    bundle = load_bundle(FIXTURES / "basic")

    assert bundle.files == ("policy.cedar",)
    assert bundle.schema_text is not None
    assert len(bundle.entities) == 3
    assert bundle.meta["policy1"].label == "refund-large"
    assert bundle.meta["policy1"].effect == "forbid"
    assert bundle.meta["policy1"].annotations["require_approval"].startswith("finance review")
    assert validate(bundle) is None


def test_template_rendering_and_missing_values() -> None:
    call = _call("c", "stripe.refund", resource_id=None)

    assert render('User::"{principal.id}"', call) == 'User::"alice"'
    assert render('Action::"{tool.name}"', call) == 'Action::"stripe.refund"'
    with pytest.raises(MissingTemplateValue) as exc_info:
        render('Resource::"{resource.id}"', call)
    assert exc_info.value.path == "resource.id"
    with pytest.raises(ValueError, match="unknown template field"):
        render("{nope}", call)
    assert render('X::"{principal.id}"', _call("c", "t", principal='a"b')) == 'X::"a\\"b"'


def test_allow_deny_approval_and_attribution(cedar: CedarEvaluator) -> None:
    prepared = cedar.prepare(FIXTURES / "basic", label="b")
    calls = [
        _call("1", "github.read"),
        _call("2", "stripe.refund", args={"amount": 750}),
        _call("3", "stripe.refund", args={"amount": 100}),
        _call("4", "github.delete_branch", context={"env": "prod"}),
        _call("5", "github.delete_branch", context={"env": "dev"}),
        _call("6", "unknown.tool"),
    ]

    d = cedar.evaluate(prepared, calls)

    assert [x.effect for x in d] == [
        Effect.ALLOW,
        Effect.REQUIRE_APPROVAL,
        Effect.ALLOW,
        Effect.DENY,
        Effect.ALLOW,
        Effect.DENY,
    ]
    assert d[0].determining == ("read-free",)
    assert d[1].reasons == ("finance review for refunds over 500",)
    assert d[1].determining == ("refund-large",)
    assert d[3].determining == ("delete-prod",)
    assert d[5].determining == ("default",)
    assert all(x.engine == "cedar" for x in d)


def test_mixed_forbids_stay_deny_when_any_lacks_the_annotation(cedar: CedarEvaluator) -> None:
    prepared = cedar.prepare(FIXTURES / "basic", label="b")

    approval, hard = cedar.evaluate(
        prepared,
        [
            _call("1", "aws.ec2.terminate_instance", context={"env": "dev"}),
            _call("2", "aws.ec2.terminate_instance", context={"env": "prod"}),
        ],
    )

    assert approval.effect is Effect.REQUIRE_APPROVAL
    assert hard.effect is Effect.DENY
    assert set(hard.determining) == {"mixed-approval", "mixed-hard"}


def test_missing_attribute_and_template_value_are_missing_context(cedar: CedarEvaluator) -> None:
    prepared = cedar.prepare(FIXTURES / "basic", label="b")

    no_dept, no_resource = cedar.evaluate(
        prepared,
        [
            _call("1", "salesforce.update", principal="bob"),
            _call("2", "github.read", resource_id=None),
        ],
    )

    assert no_dept.error_kind is ErrorKind.MISSING_CONTEXT
    assert no_dept.reasons == ("department",)
    assert no_resource.error_kind is ErrorKind.MISSING_CONTEXT
    assert "resource.id" in no_resource.reasons[0]


def test_trace_timestamp_drives_datetime_rules(cedar: CedarEvaluator) -> None:
    prepared = cedar.prepare(FIXTURES / "basic", label="b")

    day, night = cedar.evaluate(
        prepared, [_call("1", "slack.post", hour=14), _call("2", "slack.post", hour=4)]
    )

    assert day.effect is Effect.ALLOW
    assert night.effect is Effect.DENY


def test_broken_policy_marks_every_call(cedar: CedarEvaluator) -> None:
    prepared = cedar.prepare(FIXTURES / "broken", label="head")

    (d,) = cedar.evaluate(prepared, [_call("1", "x")])

    assert d.error_kind is ErrorKind.EVAL_ERROR
    assert "head" in d.reasons[0]
    assert "policy.cedar" in d.reasons[0]


def test_validation_failure_is_reported_per_file(tmp_path: Path, cedar: CedarEvaluator) -> None:
    (tmp_path / "p.cedar").write_text(
        '@id("bad")\npermit(principal, action == Action::"nope", resource);\n', encoding="utf-8"
    )
    (tmp_path / "s.cedarschema").write_text(
        (FIXTURES / "basic" / "schema.cedarschema").read_text(encoding="utf-8"), encoding="utf-8"
    )

    prepared = cedar.prepare(tmp_path, label="b")
    (d,) = cedar.evaluate(prepared, [_call("1", "github.read")])

    assert d.error_kind is ErrorKind.EVAL_ERROR
    assert "p.cedar (bad)" in d.reasons[0]


def test_custom_templates_and_registry_options() -> None:
    ev = registry.resolve("cedar", principal='Agent::"{agent.id}"', approval_annotation="needs_ok")

    assert isinstance(ev, CedarEvaluator)
    assert ev.options.principal == 'Agent::"{agent.id}"'
    assert ev.label == 'cedar Action::"{tool.name}"'
    with pytest.raises(EngineError, match="--engine cedar"):
        registry.resolve("cedar", bogus=1)


def test_missing_name_parses_cedar_errors() -> None:
    message = 'error while evaluating policy `policy5`: `User::"bob"` does not have the attribute `department`'  # noqa: E501
    assert missing_name(message) == "department"
    assert missing_name("`context` does not have the attribute `amount`") == "amount"
    assert missing_name("something else entirely") is None


def test_missing_cedarpy_names_the_install_command(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "cedarpy":
            raise ImportError("no cedarpy")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(EngineError, match=r'pip install "permdiff\[cedar\]"'):
        registry.resolve("cedar")


def test_context_carries_the_call_record_and_now() -> None:
    call = _call("c", "t", args={"amount": 1}, context={"env": "prod"})

    req = build_request(
        call,
        principal='User::"{principal.id}"',
        action='Action::"{tool.name}"',
        resource='Resource::"{resource.id}"',
        now_key="now",
    )

    assert req["context"]["amount"] == 1
    assert req["context"]["env"] == "prod"
    assert req["context"]["call"]["principal"]["id"] == "alice"
    assert req["context"]["call"]["tool"]["name"] == "t"
    assert req["context"]["now"] == {
        "__extn": {"fn": "datetime", "arg": "2026-09-20T12:00:00.000Z"}
    }


def test_nulls_are_dropped_from_the_context() -> None:
    call = _call("c", "t", args={"a": None, "b": [1, None], "c": {"d": None, "e": 2}})

    ctx = build_request(
        call,
        principal='User::"{principal.id}"',
        action='Action::"{tool.name}"',
        resource='Resource::"{resource.id}"',
        now_key="now",
    )["context"]

    assert ctx["b"] == [1]
    assert ctx["c"] == {"e": 2}
    assert "a" not in ctx
    assert "version" not in ctx["call"]["agent"]


def test_bad_template_field_is_an_engine_error_at_construction() -> None:
    with pytest.raises(EngineError, match=r"principal\.email") as exc_info:
        registry.resolve("cedar", principal='User::"{principal.email}"')

    assert "--engine cedar" in str(exc_info.value)
