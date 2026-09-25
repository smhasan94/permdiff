from __future__ import annotations

import json
from pathlib import Path

import pytest

import permdiff
from permdiff import diff, load_traces
from permdiff.errors import EngineError, PolicyError, TraceImportError
from permdiff.models import Effect, TransitionClass
from tests.conftest import GitRepo

ENGINE = "python:tests.fixtures.py_engine.rules:by_table"


def _record(i: int, tool: str, recorded: str | None = None) -> str:
    rec = {
        "id": f"c{i}",
        "timestamp": f"2026-09-2{i % 10}T12:00:00Z",
        "principal": {"id": "alice"},
        "agent": {"id": "bot"},
        "tool": {"name": tool},
    }
    if recorded:
        rec["recorded"] = {"effect": recorded}
    return json.dumps(rec)


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "a.jsonl").write_text(
        "\n".join([_record(1, "stripe.refund", "deny"), _record(2, "github.read"), "{bad"]) + "\n",
        encoding="utf-8",
    )
    (traces / "b.jsonl").write_text(_record(3, "x") + "\n", encoding="utf-8")
    return traces


def test_public_api_exports() -> None:
    assert permdiff.diff is diff
    assert permdiff.load_traces is load_traces
    assert {"ToolCall", "Decision", "Report", "Evaluator", "Transition"} <= set(permdiff.__all__)


def test_load_traces_expands_globs_in_sorted_order_and_counts_skips(corpus: Path) -> None:
    result = load_traces([str(corpus / "*.jsonl")])

    assert [c.id for c in result.calls] == ["c1", "c2", "c3"]
    assert result.stats.read == 3
    assert result.stats.skipped == 1
    assert result.stats.skipped_locators[0].startswith(str(corpus / "a.jsonl") + ":3")


def test_load_traces_accepts_explicit_paths_and_forced_format(corpus: Path) -> None:
    result = load_traces([corpus / "b.jsonl", str(corpus / "b.jsonl")], fmt="jsonl")

    assert [c.id for c in result.calls] == ["c3", "c3"]


def test_load_traces_strict_propagates(corpus: Path) -> None:
    with pytest.raises(TraceImportError, match=r"a\.jsonl:3"):
        load_traces([str(corpus / "a.jsonl")], strict=True)


def test_load_traces_unmatched_glob_names_the_flag(tmp_path: Path) -> None:
    with pytest.raises(TraceImportError, match="--traces"):
        load_traces([str(tmp_path / "none-*.jsonl")])
    with pytest.raises(TraceImportError, match="--traces"):
        load_traces([])


def test_load_traces_cap_spans_files_and_names_the_configured_cap(corpus: Path) -> None:
    # a.jsonl holds exactly 2 valid records, so the cap is filled before b.jsonl is read
    with pytest.raises(TraceImportError, match=r"b\.jsonl: corpus exceeds max_records=2 "):
        load_traces([str(corpus / "*.jsonl")], max_records=2)


def test_diff_end_to_end_on_a_git_repo(git_repo: GitRepo, corpus: Path) -> None:
    imported = load_traces([str(corpus / "*.jsonl")])

    report = diff(
        traces=imported.calls,
        base="v-base",
        head="HEAD",
        policy="policy",
        engine=ENGINE,
        repo=git_repo.path,
        salt=bytes(16),
        import_stats=imported.stats,
    )

    assert report.header.base_sha == git_repo.base_sha
    assert report.header.head_sha == git_repo.head_sha
    assert report.header.base_label == "v-base"
    assert report.header.engine == ENGINE
    assert report.header.salt == bytes(16).hex()
    assert not report.header.is_worktree
    assert report.header.window is not None
    assert report.counts.imported == 3
    assert report.counts.skipped == 1
    assert report.counts.evaluated == 3
    assert report.counts.of(TransitionClass.WIDENING) == 2
    assert report.counts.of(TransitionClass.UNCHANGED) == 1
    assert report.transitions[0].base.effect is Effect.DENY
    assert report.transitions[0].head.effect is Effect.REQUIRE_APPROVAL
    assert report.allow_widening is None


def test_diff_worktree_head_and_allow_widening(git_repo: GitRepo, corpus: Path) -> None:
    (git_repo.path / "policy" / "rules.json").write_text(
        json.dumps({"stripe.refund": "allow"}), encoding="utf-8"
    )
    imported = load_traces([str(corpus / "a.jsonl")])

    report = diff(
        traces=imported.calls,
        base="v-base",
        head="WORKTREE",
        policy="policy",
        engine=ENGINE,
        repo=git_repo.path,
        allow_widening=("ticket-1", "alice"),
    )

    assert report.header.is_worktree
    assert report.header.head_sha is None
    assert report.transitions[0].head.effect is Effect.ALLOW
    assert report.allow_widening == ("ticket-1", "alice")
    assert len(bytes.fromhex(report.header.salt)) == 16


def test_diff_without_import_stats_derives_imported(git_repo: GitRepo, corpus: Path) -> None:
    calls = load_traces([str(corpus / "b.jsonl")]).calls

    report = diff(
        traces=calls, base="v-base", head="HEAD", policy="policy", engine=ENGINE, repo=git_repo.path
    )

    assert report.counts.imported == 1
    assert report.counts.skipped == 0


def test_diff_empty_corpus_has_no_window(git_repo: GitRepo) -> None:
    report = diff(
        traces=(), base="v-base", head="HEAD", policy="policy", engine=ENGINE, repo=git_repo.path
    )

    assert report.header.window is None
    assert report.counts.evaluated == 0


def test_diff_bad_ref_and_bad_engine_raise_typed_errors(git_repo: GitRepo) -> None:
    with pytest.raises(PolicyError, match="nope"):
        diff(
            traces=(), base="nope", head="HEAD", policy="policy", engine=ENGINE, repo=git_repo.path
        )
    with pytest.raises(EngineError, match="--engine"):
        diff(traces=(), base="HEAD", head="HEAD", policy="policy", engine="opa", repo=git_repo.path)
