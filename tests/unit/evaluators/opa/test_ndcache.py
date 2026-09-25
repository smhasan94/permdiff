from __future__ import annotations

import json
from pathlib import Path

import pytest

from permdiff.errors import EngineError
from permdiff.evaluators.opa.ndcache import canonical_key, load_nd_cache, render_nd_data
from permdiff.evaluators.opa.shim import NdOverride, render_shim


def _write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "nd.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_loads_opa_shape_and_canonicalizes_keys(tmp_path: Path) -> None:
    raw = {
        "http.send": {'[{"url": "https://x", "method": "get"}]': {"status_code": 200}},
        "rand.intn": {'["dice", 6]': 3},
    }

    cache = load_nd_cache(_write(tmp_path, raw))

    assert cache.builtins == ("http.send", "rand.intn")
    assert cache.entries["http.send"] == {
        '[{"method":"get","url":"https://x"}]': {"status_code": 200}
    }
    assert cache.entries["rand.intn"] == {'["dice",6]': 3}
    assert json.loads(render_nd_data(cache))["permdiff_nd"]["rand.intn"]['["dice",6]'] == 3


def test_accepts_a_whole_decision_log_event(tmp_path: Path) -> None:
    event = {"decision_id": "x", "nd_builtin_cache": {"rand.intn": {'["d",2]': 1}}}

    assert load_nd_cache(_write(tmp_path, event)).builtins == ("rand.intn",)


@pytest.mark.parametrize(
    "payload",
    [[], {"rand.intn": 3}, {"rand.intn": {"not json": 1}}, {"rand.intn": {'{"a":1}': 1}}],
)
def test_bad_shapes_name_the_flag(tmp_path: Path, payload: object) -> None:
    with pytest.raises(EngineError, match="--nd-cache"):
        load_nd_cache(_write(tmp_path, payload))


def test_unreadable_or_invalid_json_names_the_flag(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="--nd-cache"):
        load_nd_cache(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(EngineError, match="not valid JSON"):
        load_nd_cache(bad)


def test_canonical_key_matches_opa_json_marshal() -> None:
    assert canonical_key([{"b": 1, "a": [2, 1.5, "x"]}, 3, True, None]) == (
        '[{"a":[2,1.5,"x"],"b":1},3,true,null]'
    )


def test_shim_mocks_follow_arity() -> None:
    text = render_shim(
        "data.p.d",
        nd_overrides=(
            NdOverride(builtin="rand.intn", arity=2),
            NdOverride(builtin="opa.runtime", arity=0),
        ),
    )

    assert "permdiff_mock_rand_intn(a0, a1) := resp if {" in text
    assert 'data.permdiff_nd["rand.intn"][json.marshal([a0, a1])]' in text
    assert "permdiff_mock_opa_runtime := resp if {" in text
    assert "json.marshal([])" in text
    assert (
        "with rand.intn as permdiff_mock_rand_intn with opa.runtime as permdiff_mock_opa_runtime"
        in text
    )
