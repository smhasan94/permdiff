from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from permdiff.errors import EngineError
from permdiff.evaluators import registry
from permdiff.evaluators.opa import OpaEvaluator, OpaOptions, UndefinedPolicy
from permdiff.evaluators.opa import evaluator as evaluator_module
from permdiff.evaluators.opa.binary import ENV_BIN, ENV_CACHE
from permdiff.evaluators.opa.capabilities import load_capabilities
from permdiff.models import Effect, ErrorKind, ToolCall
from tests.conftest import OPA_FIXTURES


def _call(call_id: str, tool: str, args: dict[str, Any] | None = None) -> ToolCall:
    return ToolCall.model_validate(
        {
            "id": call_id,
            "timestamp": datetime(2026, 9, 20, 14, tzinfo=UTC).isoformat(),
            "principal": {"id": "p"},
            "agent": {"id": "a"},
            "tool": {"name": tool},
            "arguments": args,
        }
    )


@pytest.fixture
def opa(opa_bin: Path) -> OpaEvaluator:
    return OpaEvaluator(OpaOptions(opa_bin=opa_bin))


def test_basic_policy_maps_objects_reasons_and_rules(opa: OpaEvaluator) -> None:
    prepared = opa.prepare(OPA_FIXTURES / "basic", label="base")
    calls = [
        _call("1", "github.read"),
        _call("2", "stripe.refund", {"amount": 750}),
        _call("3", "stripe.refund", {"amount": 100}),
        _call("4", "other.tool"),
        _call("5", "weird.tool"),
        _call("6", "string.tool"),
    ]

    d = opa.evaluate(prepared, calls)

    assert [x.call_id for x in d] == ["1", "2", "3", "4", "5", "6"]
    assert (d[0].effect, d[0].reasons, d[0].determining) == (
        Effect.ALLOW,
        ("reads are free",),
        ("read",),
    )
    assert d[1].effect is Effect.REQUIRE_APPROVAL
    assert d[1].reasons == ("amount>500", "finance review")
    assert d[1].determining == ("refund-large", "finance")
    assert d[2].effect is Effect.ALLOW
    assert d[3].effect is Effect.DENY
    assert d[3].determining == ("default",)
    assert d[4].error_kind is ErrorKind.UNSUPPORTED
    assert d[5].effect is Effect.DENY
    assert all(x.engine == "opa" for x in d)


def test_boolean_decision_path(opa_bin: Path) -> None:
    opa = OpaEvaluator(OpaOptions(opa_bin=opa_bin, decision="data.agent.authz.allow"))
    prepared = opa.prepare(OPA_FIXTURES / "bool", label="b")

    a, b = opa.evaluate(prepared, [_call("1", "github.read"), _call("2", "x")])

    assert a.effect is Effect.ALLOW
    assert b.effect is Effect.DENY


@pytest.mark.parametrize(
    ("undefined", "effect", "kind"),
    [
        (UndefinedPolicy.DENY, Effect.DENY, None),
        (UndefinedPolicy.ERROR, Effect.ERROR, ErrorKind.EVAL_ERROR),
    ],
)
def test_undefined_rule_follows_configured_policy(
    opa_bin: Path, undefined: UndefinedPolicy, effect: Effect, kind: ErrorKind | None
) -> None:
    opa = OpaEvaluator(OpaOptions(opa_bin=opa_bin, undefined=undefined))
    prepared = opa.prepare(OPA_FIXTURES / "undefined", label="b")

    defined, missing = opa.evaluate(prepared, [_call("1", "github.read"), _call("2", "x")])

    assert defined.effect is Effect.ALLOW
    assert missing.effect is effect
    assert missing.error_kind is kind
    assert "data.agent.authz.decision" in missing.reasons[0]
    assert opa.undefined_policy == undefined.value


def test_builtin_errors_are_isolated_per_call_by_bisecting(opa: OpaEvaluator) -> None:
    prepared = opa.prepare(OPA_FIXTURES / "bad_builtin", label="b")
    calls = [_call(str(i), "t", {"n": "abc" if i in (3, 7) else "5"}) for i in range(10)]

    d = opa.evaluate(prepared, calls)

    bad = [x for x in d if x.is_error]
    assert [x.call_id for x in bad] == ["3", "7"]
    assert all(x.error_kind is ErrorKind.EVAL_ERROR for x in bad)
    assert "to_number" in bad[0].reasons[0]
    assert all(x.effect is Effect.ALLOW for x in d if not x.is_error)


def test_bisect_cap_marks_remaining_failures_wholesale(
    opa: OpaEvaluator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(evaluator_module, "MAX_BISECT_FAILURES", 1)
    prepared = opa.prepare(OPA_FIXTURES / "bad_builtin", label="b")
    calls = [_call(str(i), "t", {"n": "abc"}) for i in range(6)]

    d = opa.evaluate(prepared, calls)

    assert all(x.error_kind is ErrorKind.EVAL_ERROR for x in d)
    assert any("bisect cap" in x.reasons[0] for x in d)


def test_compile_failure_marks_every_call_eval_error(opa: OpaEvaluator, tmp_path: Path) -> None:
    (tmp_path / "broken.rego").write_text("package x\n\nthis is not rego\n", encoding="utf-8")

    prepared = opa.prepare(tmp_path, label="head")
    d = opa.evaluate(prepared, [_call("1", "t")])

    assert d[0].error_kind is ErrorKind.EVAL_ERROR
    assert "failed to compile" in d[0].reasons[0]
    assert "head" in d[0].reasons[0]


def test_v0_compatible_flag(opa_bin: Path) -> None:
    modern = OpaEvaluator(OpaOptions(opa_bin=opa_bin))
    legacy = OpaEvaluator(OpaOptions(opa_bin=opa_bin, v0_compatible=True))

    assert modern.prepare(OPA_FIXTURES / "v0", label="b").compile_error is not None  # type: ignore[attr-defined]
    prepared = legacy.prepare(OPA_FIXTURES / "v0", label="b")
    (d,) = legacy.evaluate(prepared, [_call("1", "github.read")])
    assert d.effect is Effect.ALLOW


def test_empty_corpus_and_label(opa: OpaEvaluator) -> None:
    prepared = opa.prepare(OPA_FIXTURES / "basic", label="b")

    assert opa.evaluate(prepared, []) == ()
    assert opa.label == "opa data.agent.authz.decision"
    prepared.close()


def test_wrong_prepared_type_is_a_type_error(opa: OpaEvaluator) -> None:
    class Other:
        label = "x"

        def close(self) -> None:
            return None

    with pytest.raises(TypeError):
        opa.evaluate(Other(), [_call("1", "t")])


def test_registry_builds_opa_with_options(opa_bin: Path) -> None:
    ev = registry.resolve("opa", opa_bin=opa_bin, decision="data.a.b", undefined="error")

    assert isinstance(ev, OpaEvaluator)
    assert ev.options.decision == "data.a.b"
    assert ev.options.undefined is UndefinedPolicy.ERROR
    assert "opa" in registry.names()


def test_registry_rejects_bad_opa_options() -> None:
    with pytest.raises(EngineError, match="--engine opa"):
        registry.resolve("opa", decision="not-a-path")
    with pytest.raises(EngineError, match="--engine opa"):
        registry.resolve("opa", bogus=1)


def _call_at(call_id: str, hour: int) -> ToolCall:
    return ToolCall.model_validate(
        {
            "id": call_id,
            "timestamp": datetime(2026, 9, 20, hour, tzinfo=UTC).isoformat(),
            "principal": {"id": "p"},
            "agent": {"id": "a"},
            "tool": {"name": "t"},
        }
    )


def test_trace_timestamp_drives_time_dependent_rules(opa: OpaEvaluator) -> None:
    prepared = opa.prepare(OPA_FIXTURES / "hours", label="b")

    day, night = opa.evaluate(prepared, [_call_at("day", 14), _call_at("night", 4)])

    assert day.effect is Effect.ALLOW
    assert night.effect is Effect.REQUIRE_APPROVAL


def test_denied_builtin_makes_every_call_nondeterministic(opa: OpaEvaluator) -> None:
    prepared = opa.prepare(OPA_FIXTURES / "http", label="head")

    d = opa.evaluate(prepared, [_call("1", "t"), _call("2", "t")])

    assert all(x.error_kind is ErrorKind.NONDETERMINISTIC for x in d)
    assert "http.send" in d[0].reasons[0]
    assert "head" in d[0].reasons[0]


def _nd_file(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "nd.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_nd_cache_replays_recorded_http_response(opa_bin: Path, tmp_path: Path) -> None:
    nd = _nd_file(
        tmp_path,
        {
            "http.send": {
                '[{"method":"get","url":"https://risk.example/score"}]': {"body": {"score": 10}}
            }
        },
    )
    opa = OpaEvaluator(OpaOptions(opa_bin=opa_bin, nd_cache=nd))
    prepared = opa.prepare(OPA_FIXTURES / "http", label="b")

    (d,) = opa.evaluate(prepared, [_call("1", "t")])

    assert d.effect is Effect.ALLOW
    assert d.reasons == ("low risk",)


def test_nd_cache_miss_is_nondeterministic_and_names_the_lookup(
    opa_bin: Path, tmp_path: Path
) -> None:
    nd = _nd_file(
        tmp_path, {"http.send": {'[{"method":"get","url":"https://other"}]': {"body": {}}}}
    )
    opa = OpaEvaluator(OpaOptions(opa_bin=opa_bin, nd_cache=nd))
    prepared = opa.prepare(OPA_FIXTURES / "http", label="b")

    (d,) = opa.evaluate(prepared, [_call("1", "t")])

    assert d.error_kind is ErrorKind.NONDETERMINISTIC
    assert "missing from --nd-cache" in d.reasons[0]
    assert "risk.example" in d.reasons[0]


def test_nd_cache_two_argument_builtin(opa_bin: Path, tmp_path: Path) -> None:
    nd = _nd_file(tmp_path, {"rand.intn": {'["dice", 6]': 5}})
    opa = OpaEvaluator(OpaOptions(opa_bin=opa_bin, nd_cache=nd))
    prepared = opa.prepare(OPA_FIXTURES / "rand", label="b")

    (d,) = opa.evaluate(prepared, [_call("1", "t")])

    assert d.effect is Effect.ALLOW
    assert d.reasons == ("lucky",)


def test_nd_cache_does_not_unlock_other_denied_builtins(opa_bin: Path, tmp_path: Path) -> None:
    nd = _nd_file(tmp_path, {"rand.intn": {'["dice", 6]': 5}})
    opa = OpaEvaluator(OpaOptions(opa_bin=opa_bin, nd_cache=nd))
    prepared = opa.prepare(OPA_FIXTURES / "http", label="b")

    (d,) = opa.evaluate(prepared, [_call("1", "t")])

    assert d.error_kind is ErrorKind.NONDETERMINISTIC
    assert "http.send" in d.reasons[0]


def test_explicit_capabilities_file_is_used_as_is(opa_bin: Path, tmp_path: Path) -> None:
    full = tmp_path / "full.json"
    full.write_text(json.dumps(load_capabilities(opa_bin)), encoding="utf-8")
    opa = OpaEvaluator(OpaOptions(opa_bin=opa_bin, capabilities=full))

    prepared = opa.prepare(OPA_FIXTURES / "http", label="b")

    assert prepared.compile_error is None  # type: ignore[attr-defined]


def test_evaluator_env_scopes_cache_and_binary_lookup(opa_bin: Path, tmp_path: Path) -> None:
    env = {ENV_BIN: str(opa_bin), ENV_CACHE: str(tmp_path / "scoped")}
    opa = OpaEvaluator(OpaOptions(env=env))

    prepared = opa.prepare(OPA_FIXTURES / "basic", label="b")

    assert prepared.compile_error is None  # type: ignore[attr-defined]
    assert opa.binary == opa_bin
    assert (tmp_path / "scoped" / "opa" / "capabilities").is_dir()
