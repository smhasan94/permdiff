"""Public Python API (FR-27): ``load_traces`` and ``diff``."""

from __future__ import annotations

import glob
import logging
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from permdiff.errors import TraceImportError
from permdiff.evaluators import registry as engines
from permdiff.importers import registry as importers
from permdiff.importers.base import ImportResult, ImportStats
from permdiff.models import Counts, Report, ReportHeader, ToolCall
from permdiff.models.limits import DEFAULT_MAX_RECORDS
from permdiff.policy import PolicySource, source_for
from permdiff.redact import new_salt
from permdiff.replay import replay

log = logging.getLogger(__name__)

AUTO_FORMAT = "auto"


def _expand(patterns: Sequence[str | Path]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        text = str(pattern)
        matches = sorted(glob.glob(text)) if glob.has_magic(text) else [text]  # noqa: PTH207
        if not matches:
            msg = f"--traces {text!r} matched no files"
            raise TraceImportError(msg)
        paths.extend(Path(m) for m in matches)
    if not paths:
        msg = "no trace files given; pass --traces FILE|GLOB"
        raise TraceImportError(msg)
    return paths


def load_traces(
    paths: Sequence[str | Path],
    *,
    fmt: str = AUTO_FORMAT,
    strict: bool = False,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> ImportResult:
    """Read every file (globs expanded) into canonical calls, in path order.

    ``fmt`` is an importer name or ``auto`` to sniff each file (FR-5).
    """
    calls: list[ToolCall] = []
    read = skipped = 0
    locators: list[str] = []
    started = time.perf_counter()
    for path in _expand(paths):
        importer = importers.detect(path) if fmt == AUTO_FORMAT else importers.get(fmt)
        result = importer.read(path, strict=strict, max_records=max_records)
        calls.extend(result.calls)
        if len(calls) > max_records:
            msg = (
                f"{path}: corpus exceeds max_records={max_records} across --traces files; "
                "raise the cap or split the run"
            )
            raise TraceImportError(msg)
        read += result.stats.read
        skipped += result.stats.skipped
        locators.extend(result.stats.skipped_locators)
    log.info(
        "imported %d calls (%d skipped) in %.2fs", read, skipped, time.perf_counter() - started
    )
    stats = ImportStats(read=read, skipped=skipped, skipped_locators=tuple(locators))
    return ImportResult(calls=tuple(calls), stats=stats)


def diff(
    *,
    traces: Sequence[ToolCall],
    base: str,
    head: str,
    policy: str,
    engine: str,
    repo: Path = Path(),
    engine_options: Mapping[str, Any] | None = None,
    salt: bytes | None = None,
    verify_deterministic: bool = False,
    keep_temp: bool = False,
    import_stats: ImportStats | None = None,
    filtered: int = 0,
    allow_widening: tuple[str, str] | None = None,
) -> Report:
    """Replay ``traces`` against ``policy`` at ``base`` and ``head``; return an unredacted Report.

    Apply a ``Redactor`` built with the same ``salt`` before rendering.
    """
    return diff_sources(
        traces=traces,
        base=source_for(repo, base, policy),
        head=source_for(repo, head, policy),
        policy_path=policy,
        engine=engine,
        engine_options=engine_options,
        salt=salt,
        verify_deterministic=verify_deterministic,
        keep_temp=keep_temp,
        import_stats=import_stats,
        filtered=filtered,
        allow_widening=allow_widening,
    )


def diff_sources(
    *,
    traces: Sequence[ToolCall],
    base: PolicySource,
    head: PolicySource,
    policy_path: str,
    engine: str,
    engine_options: Mapping[str, Any] | None = None,
    salt: bytes | None = None,
    verify_deterministic: bool = False,
    keep_temp: bool = False,
    import_stats: ImportStats | None = None,
    filtered: int = 0,
    allow_widening: tuple[str, str] | None = None,
) -> Report:
    """``diff`` over explicit policy sources (git refs, the worktree, or plain directories)."""
    evaluator = engines.resolve(engine, **dict(engine_options or {}))
    run_salt = salt if salt is not None else new_salt()
    started = time.perf_counter()
    with (
        base.materialize(keep=keep_temp) as base_policy,
        head.materialize(keep=keep_temp) as head_policy,
    ):
        log.info("materialized policies in %.2fs", time.perf_counter() - started)
        started = time.perf_counter()
        result = replay(
            traces,
            evaluator,
            base_policy,
            head_policy,
            verify_deterministic=verify_deterministic,
        )
        log.info(
            "evaluated %d calls at both refs in %.2fs", len(traces), time.perf_counter() - started
        )
        header = ReportHeader(
            base_label=base_policy.label,
            base_sha=base_policy.sha,
            head_label=head_policy.label,
            head_sha=head_policy.sha,
            is_worktree=head_policy.is_worktree,
            policy_path=policy_path,
            engine=getattr(evaluator, "label", evaluator.name),
            window=_window(traces),
            salt=run_salt.hex(),
            undefined_policy=getattr(evaluator, "undefined_policy", None),
            generated_at=datetime.now(tz=UTC),
        )
    counts = _merge_counts(result.counts, import_stats, filtered)
    return Report(
        header=header, transitions=result.transitions, counts=counts, allow_widening=allow_widening
    )


def _window(traces: Sequence[ToolCall]) -> tuple[datetime, datetime] | None:
    if not traces:
        return None
    stamps = [t.timestamp for t in traces]
    return min(stamps), max(stamps)


def _merge_counts(counts: Counts, stats: ImportStats | None, filtered: int) -> Counts:
    imported = stats.read if stats else counts.evaluated + filtered
    skipped = stats.skipped if stats else 0
    return counts.model_copy(
        update={"imported": imported, "skipped": skipped, "filtered": filtered}
    )
