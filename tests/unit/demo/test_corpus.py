from __future__ import annotations

import importlib.util
from pathlib import Path

from permdiff import demo
from permdiff.importers.jsonl import JsonlImporter
from tests.redaction_harness import assert_no_sentinels

GENERATOR = Path(__file__).parents[3] / "scripts" / "gen_demo_corpus.py"


def _generator_render() -> str:
    spec = importlib.util.spec_from_file_location("gen_demo_corpus", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result: str = module.render()
    return result


def test_checked_in_corpus_matches_the_generator() -> None:
    assert demo.CORPUS.read_text(encoding="utf-8") == _generator_render(), (
        "regenerate with `uv run python scripts/gen_demo_corpus.py`"
    )


def test_corpus_has_200_valid_calls_and_no_pii_like_data() -> None:
    result = JsonlImporter().read(demo.CORPUS, strict=True)

    assert result.stats.read == 200
    assert result.stats.skipped == 0
    text = demo.CORPUS.read_text(encoding="utf-8")
    assert_no_sentinels(text)
    assert "@" not in text
    principals = {c.principal.id for c in result.calls}
    assert all(p.split("-")[0] in {"support", "ops", "finance", "sales"} for p in principals)


def test_corpus_is_sorted_by_timestamp_with_unique_ids() -> None:
    calls = JsonlImporter().read(demo.CORPUS).calls

    assert [c.timestamp for c in calls] == sorted(c.timestamp for c in calls)
    assert len({c.id for c in calls}) == 200
