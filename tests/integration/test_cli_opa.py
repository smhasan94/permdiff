from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner, Result

from permdiff.cli.main import cli
from tests.conftest import HEAD_REGO


def _run(repo: Path, traces: Path, opa_bin: Path, *extra: str) -> Result:
    args = [
        "diff",
        "--repo",
        str(repo),
        "--base",
        "v-base",
        "--head",
        "HEAD",
        "--engine",
        "opa",
        "--opa-bin",
        str(opa_bin),
        "--traces",
        str(traces),
        "--no-color",
        *extra,
    ]
    return CliRunner().invoke(cli, args)


def test_opa_diff_end_to_end(rego_repo: Path, traces: Path, opa_bin: Path) -> None:
    result = _run(rego_repo, traces, opa_bin)

    assert result.exit_code == 2, result.output
    out = result.stdout
    assert "engine opa data.agent.authz.decision" in out
    assert "newly ALLOWED               1   github.delete_branch   ⚠ widening" in out
    assert "now REQUIRE_APPROVAL        1   stripe.refund" in out
    assert (
        "attribution changed         1   stripe.refund" in out
    )  # rule renamed refund → refund-small
    assert "unchanged                   1" in out
    assert "[amount>500]" in out


def test_opa_diff_custom_decision_path_and_undefined_error(
    rego_repo: Path, traces: Path, opa_bin: Path
) -> None:
    result = _run(
        rego_repo, traces, opa_bin, "--decision", "data.agent.authz.nope", "--undefined", "error"
    )

    assert result.exit_code == 0, result.output
    assert (
        "can't evaluate              4   eval error: data.agent.authz.nope is undefined"
        in result.stdout
    )


def test_opa_diff_bad_decision_path_names_flag(
    rego_repo: Path, traces: Path, opa_bin: Path
) -> None:
    result = _run(rego_repo, traces, opa_bin, "--decision", "agent.authz")

    assert result.exit_code == 1
    assert "--decision" in result.stderr


def test_opa_diff_missing_binary_names_overrides(
    rego_repo: Path, traces: Path, tmp_path: Path
) -> None:
    result = _run(rego_repo, traces, tmp_path / "no-opa")

    assert result.exit_code == 1
    assert "--opa-bin" in result.stderr


def test_opa_diff_nd_cache_flag(
    rego_repo: Path, traces: Path, opa_bin: Path, tmp_path: Path
) -> None:
    delete_rule = HEAD_REGO.splitlines()[-1]  # the github.delete_branch allow rule
    lookup_rule = "\n".join(
        [
            'decision := {"effect": "allow", "rule": "delete"} if {',
            '    input.tool.name == "github.delete_branch"',
            '    http.send({"method": "get", "url": "https://risk.example/ok"}).status_code == 200',
            "}",
        ]
    )
    (rego_repo / "policy" / "agent.rego").write_text(
        HEAD_REGO.replace(delete_rule, lookup_rule), encoding="utf-8"
    )
    nd = tmp_path / "nd.json"
    nd.write_text(
        json.dumps(
            {
                "http.send": {
                    '[{"method":"get","url":"https://risk.example/ok"}]': {"status_code": 200}
                }
            }
        ),
        encoding="utf-8",
    )

    without = _run(rego_repo, traces, opa_bin, "--head", "WORKTREE")
    with_cache = _run(rego_repo, traces, opa_bin, "--head", "WORKTREE", "--nd-cache", str(nd))

    assert (
        "nondeterministic: policy at WORKTREE uses nondeterministic builtin http.send"
        in without.stdout
    )
    assert with_cache.exit_code == 2, with_cache.output
    assert "newly ALLOWED               1   github.delete_branch   ⚠ widening" in with_cache.stdout
