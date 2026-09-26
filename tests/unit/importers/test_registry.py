from __future__ import annotations

import json
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

from permdiff.errors import TraceImportError
from permdiff.importers import registry
from permdiff.importers.base import ImportResult, ImportStats
from permdiff.importers.jsonl import JsonlImporter


class FakeImporter:
    name = "fake"

    def detect(self, head: bytes) -> bool:
        return head.startswith(b"FAKE")

    def read(self, path: Path, *, strict: bool = False, max_records: int = 0) -> ImportResult:
        return ImportResult(calls=(), stats=ImportStats(read=0, skipped=0, skipped_locators=()))


@pytest.fixture
def fake_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    ep = EntryPoint(name="fake", value=f"{__name__}:FakeImporter", group=registry.ENTRY_POINT_GROUP)
    monkeypatch.setattr(registry, "_entry_points", lambda: (ep,))


def test_get_returns_builtin_jsonl_importer() -> None:
    assert isinstance(registry.get("jsonl"), JsonlImporter)
    assert isinstance(registry.get("permdiff"), JsonlImporter)


def test_get_unknown_name_lists_available_importers() -> None:
    with pytest.raises(TraceImportError, match="jsonl") as exc_info:
        registry.get("nope")

    assert "--from" in str(exc_info.value)


def test_names_include_entry_point_importers(fake_entry_point: None) -> None:
    assert "fake" in registry.names()
    assert isinstance(registry.get("fake"), FakeImporter)


def test_builtin_name_wins_over_entry_point_collision(monkeypatch: pytest.MonkeyPatch) -> None:
    ep = EntryPoint(
        name="jsonl", value=f"{__name__}:FakeImporter", group=registry.ENTRY_POINT_GROUP
    )
    monkeypatch.setattr(registry, "_entry_points", lambda: (ep,))

    assert isinstance(registry.get("jsonl"), JsonlImporter)


def test_detect_picks_jsonl_for_permdiff_records(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    record = {
        "id": "c1",
        "timestamp": "2026-09-20T14:03:11Z",
        "principal": {"id": "a"},
        "agent": {"id": "b"},
        "tool": {"name": "t"},
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    assert isinstance(registry.detect(path), JsonlImporter)


def test_detect_consults_entry_point_importers(fake_entry_point: None, tmp_path: Path) -> None:
    path = tmp_path / "t.fake"
    path.write_bytes(b"FAKE data")

    assert isinstance(registry.detect(path), FakeImporter)


def test_detect_fails_with_path_and_hint_when_unrecognized(tmp_path: Path) -> None:
    path = tmp_path / "mystery.txt"
    path.write_text("hello\n", encoding="utf-8")

    with pytest.raises(TraceImportError, match=r"mystery\.txt") as exc_info:
        registry.detect(path)

    assert "--from" in str(exc_info.value)


def test_detect_missing_file_is_an_import_error(tmp_path: Path) -> None:
    with pytest.raises(TraceImportError, match=r"missing\.jsonl"):
        registry.detect(tmp_path / "missing.jsonl")


class NotAnImporter:
    name = "broken"


def _boom() -> None:
    raise RuntimeError("plugin exploded")


def test_broken_entry_points_are_ignored_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    eps = (
        EntryPoint(name="crash", value=f"{__name__}:_boom", group=registry.ENTRY_POINT_GROUP),
        EntryPoint(
            name="shape", value=f"{__name__}:NotAnImporter", group=registry.ENTRY_POINT_GROUP
        ),
        EntryPoint(name="gone", value="no_such_module_xyz:Thing", group=registry.ENTRY_POINT_GROUP),
    )
    monkeypatch.setattr(registry, "_entry_points", lambda: eps)

    with caplog.at_level("WARNING", logger=registry.__name__):
        assert registry.names() == (
            "jsonl",
            "custody",
            "otel",
            "claude-code-hooks",
            "claude-code",
            "opa-decision-log",
        )

    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "crash" in messages
    assert "not an Importer" in messages
    assert "gone" in messages
