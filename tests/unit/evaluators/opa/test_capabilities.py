from __future__ import annotations

import json
from pathlib import Path

import pytest

from permdiff.errors import EngineError
from permdiff.evaluators.opa import capabilities as caps


def _names(path: Path) -> set[str]:
    return {b["name"] for b in json.loads(path.read_text(encoding="utf-8"))["builtins"]}


def test_restricted_file_omits_denied_builtins_and_keeps_the_rest(
    opa_bin: Path, tmp_path: Path
) -> None:
    path = caps.restricted_capabilities(opa_bin, cache_root=tmp_path)

    names = _names(path)
    assert not names & set(caps.DENIED_BUILTINS)
    assert {"time.now_ns", "json.marshal", "time.clock", "count"} <= names
    assert path.parent == tmp_path / "opa" / "capabilities"


def test_restricted_file_is_cached_and_allow_changes_the_file(
    opa_bin: Path, tmp_path: Path
) -> None:
    a = caps.restricted_capabilities(opa_bin, cache_root=tmp_path)
    again = caps.restricted_capabilities(opa_bin, cache_root=tmp_path)
    with_http = caps.restricted_capabilities(opa_bin, allow=("http.send",), cache_root=tmp_path)

    assert a == again
    assert with_http != a
    assert "http.send" in _names(with_http)
    assert "rand.intn" not in _names(with_http)


def test_builtin_arity_from_capabilities(opa_bin: Path) -> None:
    assert caps.builtin_arity(opa_bin, "http.send") == 1
    assert caps.builtin_arity(opa_bin, "rand.intn") == 2
    assert caps.builtin_arity(opa_bin, "opa.runtime") == 0
    with pytest.raises(EngineError, match="--nd-cache"):
        caps.builtin_arity(opa_bin, "no.such.builtin")


def test_load_capabilities_failure_is_an_engine_error(tmp_path: Path) -> None:
    fake = tmp_path / "opa"
    fake.write_text("#!/bin/sh\necho nope >&2\nexit 3\n", encoding="utf-8")
    fake.chmod(0o755)

    with pytest.raises(EngineError, match="opa capabilities failed"):
        caps.load_capabilities(fake)
