from __future__ import annotations

import pytest

from permdiff.importers.claude_code.mapping import (
    UNKNOWN_PRINCIPAL,
    principal_of,
    resource_of,
    split_tool,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Bash", (None, None)),
        ("mcp__github__create_issue", ("github", "mcp")),
        ("mcp__my-server__some__tool", ("my-server", "mcp")),
        ("mcp__", (None, None)),
        ("mcp__only", (None, None)),
    ],
)
def test_split_tool(name: str, expected: tuple[str | None, str | None]) -> None:
    assert split_tool(name) == expected


@pytest.mark.parametrize(
    ("tool", "arguments", "expected"),
    [
        ("Bash", {"command": "ls"}, {"type": "shell"}),
        ("Read", {"file_path": "/p/a.py"}, {"type": "file", "id": "/p/a.py"}),
        ("NotebookEdit", {"notebook_path": "/p/n.ipynb"}, {"type": "file", "id": "/p/n.ipynb"}),
        ("Grep", {"pattern": "x", "path": "/p/src"}, {"type": "file", "id": "/p/src"}),
        ("WebFetch", {"url": "https://e.com/x"}, {"type": "url", "id": "https://e.com/x"}),
        ("Glob", {"pattern": "**/*.py"}, {}),
        ("Read", None, {}),
        ("Read", {"file_path": 3}, {}),
    ],
)
def test_resource_of(
    tool: str, arguments: dict[str, object] | None, expected: dict[str, str]
) -> None:
    assert resource_of(tool, arguments) == expected


def test_principal_of_env_key_and_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERMDIFF_TEST_USER", "dev-user")
    monkeypatch.delenv("PERMDIFF_TEST_MISSING", raising=False)
    record = {"userType": "external", "empty": ""}

    assert principal_of(record, "env:PERMDIFF_TEST_USER") == ("dev-user", True)
    assert principal_of(record, "env:PERMDIFF_TEST_MISSING") == (UNKNOWN_PRINCIPAL, False)
    assert principal_of(record, "userType") == ("external", True)
    assert principal_of(record, "empty") == (UNKNOWN_PRINCIPAL, False)
    assert principal_of(record, "absent") == (UNKNOWN_PRINCIPAL, False)
    assert principal_of(record, None) == (UNKNOWN_PRINCIPAL, False)
