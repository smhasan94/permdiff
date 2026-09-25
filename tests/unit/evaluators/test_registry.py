from __future__ import annotations

from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

import pytest

from permdiff.errors import EngineError
from permdiff.evaluators import registry
from permdiff.evaluators.base import PreparedPolicy
from permdiff.evaluators.python_callable import PythonCallableEvaluator
from permdiff.models import Decision

FIXTURES = "tests.fixtures.py_engine.rules"


class FakePrepared:
    label = "x"

    def close(self) -> None:
        return None


class FakeEvaluator:
    name = "fake"

    def __init__(self, **options: Any) -> None:
        self.options = options

    def prepare(self, policy_dir: Path, *, label: str) -> PreparedPolicy:
        return FakePrepared()

    def evaluate(self, prepared: PreparedPolicy, calls: Any) -> tuple[Decision, ...]:
        return ()


def _fake_entry_point(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    ep = EntryPoint(name=name, value=value, group=registry.ENTRY_POINT_GROUP)
    monkeypatch.setattr(registry, "_entry_points", lambda: (ep,))


def test_resolve_python_spec_loads_the_callable() -> None:
    ev = registry.resolve(f"python:{FIXTURES}:allow_all")

    assert isinstance(ev, PythonCallableEvaluator)
    assert ev.name == f"python:{FIXTURES}:allow_all"


@pytest.mark.parametrize(
    ("spec", "fragment"),
    [
        ("python:no_such_module_xyz:fn", "no_such_module_xyz"),
        (f"python:{FIXTURES}:missing_fn", "missing_fn"),
        (f"python:{FIXTURES}:not_callable", "not callable"),
        ("python:onlymodule", "python:module.path:callable"),
        ("python:", "python:module.path:callable"),
    ],
)
def test_bad_python_spec_names_the_spec_and_problem(spec: str, fragment: str) -> None:
    with pytest.raises(EngineError, match=fragment) as exc_info:
        registry.resolve(spec)

    assert spec in str(exc_info.value)


def test_unknown_engine_lists_available_and_mentions_python_form() -> None:
    with pytest.raises(EngineError, match="--engine") as exc_info:
        registry.resolve("opa")

    assert "python:module.path:callable" in str(exc_info.value)


def test_entry_point_evaluator_receives_options(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_entry_point(monkeypatch, "fake", f"{__name__}:FakeEvaluator")

    ev = registry.resolve("fake", decision="data.x")

    assert isinstance(ev, FakeEvaluator)
    assert ev.options == {"decision": "data.x"}
    assert "fake" in registry.names()


def test_entry_point_that_fails_to_load_is_an_engine_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_entry_point(monkeypatch, "fake", "no_such_module_xyz:Thing")

    with pytest.raises(EngineError, match="fake"):
        registry.resolve("fake")


def test_entry_point_returning_non_evaluator_is_an_engine_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_entry_point(monkeypatch, "fake", f"{__name__}:FakePrepared")

    with pytest.raises(EngineError, match="Evaluator"):
        registry.resolve("fake")
