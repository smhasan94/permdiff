from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from hypothesis import given, settings

from permdiff.cli.convert import to_jsonl_line
from permdiff.cli.main import cli
from permdiff.importers.jsonl import JsonlImporter
from permdiff.models import ToolCall
from tests.conftest import OPA_FIXTURES
from tests.strategies import tool_calls

FIXTURES = OPA_FIXTURES.parent


def test_convert_otel_and_custody_round_trip_through_jsonl(tmp_path: Path) -> None:
    out = tmp_path / "otel.jsonl"
    result = CliRunner().invoke(
        cli,
        ["convert", "--from", "otel", str(FIXTURES / "otel" / "execute_tool.json"), "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert "converted 3 calls (0 skipped)" in result.stderr
    reread = JsonlImporter().read(out, strict=True)
    assert [c.tool.name for c in reread.calls] == ["stripe.refund", "github.read", "slack.post"]
    assert reread.calls[0].source is not None
    assert reread.calls[0].source.format == "otel.genai"

    custody = CliRunner().invoke(
        cli, ["convert", "--from", "custody", str(FIXTURES / "custody" / "all_types.jsonl")]
    )
    assert custody.exit_code == 0
    assert len(custody.stdout.splitlines()) == 8
    assert json.loads(custody.stdout.splitlines()[0])["recorded"]["effect"] == "deny"


def test_convert_auto_detects_and_reports_mismatch(tmp_path: Path) -> None:
    auto = CliRunner().invoke(cli, ["convert", str(FIXTURES / "custody" / "digest_only.jsonl")])
    wrong = CliRunner().invoke(
        cli, ["convert", "--from", "jsonl", str(FIXTURES / "custody" / "digest_only.jsonl")]
    )

    assert auto.exit_code == 0, auto.output
    assert json.loads(auto.stdout)["arguments"] is None
    assert wrong.exit_code == 1
    assert "looks like custody traces, not jsonl" in wrong.stderr


def test_convert_strict_and_principal_from(tmp_path: Path) -> None:
    strict = CliRunner().invoke(
        cli,
        ["convert", "--from", "otel", "--strict", str(FIXTURES / "otel" / "execute_tool.jsonl")],
    )
    principal = CliRunner().invoke(
        cli,
        [
            "convert",
            "--from",
            "otel",
            "--principal-from",
            "resource.attr.service.name",
            str(FIXTURES / "otel" / "execute_tool.json"),
        ],
    )

    assert strict.exit_code == 1
    assert "bbbb000000000003" in strict.stderr
    assert principal.exit_code == 0
    assert {json.loads(line)["principal"]["id"] for line in principal.stdout.splitlines()} == {
        "support-bot"
    }


@settings(max_examples=40, deadline=None)
@given(tool_calls())
def test_any_call_survives_the_jsonl_round_trip(call: ToolCall) -> None:
    line = to_jsonl_line(call)

    reread = ToolCall.model_validate_json(line)
    assert reread.model_copy(update={"source": None}) == call.model_copy(update={"source": None})


def test_convert_unwritable_output_is_a_clean_error(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "convert",
            "--from",
            "custody",
            str(FIXTURES / "custody" / "digest_only.jsonl"),
            "-o",
            str(tmp_path / "missing-dir" / "out.jsonl"),
        ],
    )

    assert result.exit_code == 1
    assert "error: cannot write" in result.stderr


def test_convert_claude_code_transcripts_and_hook_logs(tmp_path: Path) -> None:
    claude_code = FIXTURES / "claude_code"
    for name, fmt, count in (
        ("session.jsonl", "claude-code", 7),
        ("hooks.jsonl", "claude-code-hooks", 2),
    ):
        out = tmp_path / f"{fmt}.jsonl"
        result = CliRunner().invoke(cli, ["convert", str(claude_code / name), "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert f"converted {count} calls (0 skipped)" in result.stderr
        reread = JsonlImporter().read(out, strict=True)
        assert len(reread.calls) == count
        assert reread.calls[0].source is not None
        assert reread.calls[0].source.format == fmt
        assert reread.calls[0].tool.name == "Bash"


OPA_LOG = FIXTURES / "opa_log"


def test_convert_nd_cache_out_merges_the_events_caches(tmp_path: Path) -> None:
    nd = tmp_path / "nd.json"

    result = CliRunner().invoke(
        cli,
        [
            "convert",
            str(OPA_LOG / "console.jsonl"),
            "-o",
            str(tmp_path / "c.jsonl"),
            "--nd-cache-out",
            str(nd),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "converted 3 calls (1 skipped)" in result.stderr
    assert "merged nd_builtin_cache from 1 of 3 calls into" in result.stderr
    assert "1 builtin, 0 conflicts" in result.stderr
    assert json.loads(nd.read_text()) == {"rand.intn": {'["x",10]': 2}}


def test_convert_nd_cache_out_reports_conflicts_and_strict_aborts(tmp_path: Path) -> None:
    def event(call_id: str, value: int) -> dict[str, object]:
        return {
            "decision_id": f"d-{call_id}",
            "path": "agent/authz/decision",
            "input": {
                "id": call_id,
                "timestamp": "2026-09-26T00:00:00Z",
                "principal": {"id": "u"},
                "agent": {"id": "a"},
                "tool": {"name": "t"},
            },
            "result": True,
            "nd_builtin_cache": {"rand.intn": {'["x",10]': value}},
            "timestamp": "2026-09-26T00:00:01Z",
        }

    log = tmp_path / "log.json"
    log.write_text(json.dumps([event("c1", 2), event("c2", 5)]))
    nd = tmp_path / "nd.json"

    lenient = CliRunner().invoke(
        cli, ["convert", str(log), "-o", str(tmp_path / "c.jsonl"), "--nd-cache-out", str(nd)]
    )
    strict = CliRunner().invoke(
        cli,
        [
            "convert",
            str(log),
            "-o",
            str(tmp_path / "c2.jsonl"),
            "--nd-cache-out",
            str(tmp_path / "nd2.json"),
            "--strict",
        ],
    )

    assert lenient.exit_code == 0, lenient.output
    assert "1 conflict" in lenient.stderr
    assert 'rand.intn ["x",10]: kept 2 from d-c1, dropped 5 from d-c2' in lenient.stderr
    assert json.loads(nd.read_text()) == {"rand.intn": {'["x",10]': 2}}
    assert strict.exit_code == 1
    assert "conflict" in strict.stderr
    assert not (tmp_path / "nd2.json").exists()
