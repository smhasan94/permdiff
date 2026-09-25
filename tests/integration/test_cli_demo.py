from __future__ import annotations

import time

from click.testing import CliRunner, Result

from permdiff.cli.main import cli

DEMO_BUDGET_SECONDS = 5.0


def _run(*args: str) -> Result:
    return CliRunner().invoke(cli, ["demo", "--engine", "python", "--no-color", *args])


def test_demo_exits_two_and_shows_every_transition_kind() -> None:
    started = time.perf_counter()
    result = _run("--salt", "00")
    elapsed = time.perf_counter() - started

    assert result.exit_code == 2, result.output
    assert elapsed < DEMO_BUDGET_SECONDS
    out = result.stdout
    assert "permdiff: demo/base → demo/head   (200 calls, 2026-09-18 → 2026-09-24)" in out
    assert "  policy demo/policy  engine python:permdiff.demo.engine:evaluate" in out
    assert "newly DENIED               15   aws.ec2.terminate_instance" in out
    assert "newly ALLOWED               6   github.delete_branch   ⚠ widening" in out
    assert "now REQUIRE_APPROVAL       22   stripe.refund" in out
    assert "can't evaluate              5   missing context: principal.attrs.department" in out
    assert "unchanged                 152" in out
    assert "attribution changed" not in out
    assert "exit 2 (widening found; --fail-on widen)" in out


def test_demo_groups_cover_widening_tightening_approval_and_errors() -> None:
    out = _run().stdout

    assert "widening  github.delete_branch  (6 calls)   deny → allow" in out
    assert "tightening  stripe.refund  (22 calls)   allow → require_approval" in out
    assert "tightening  aws.ec2.terminate_instance  (15 calls)   allow → deny" in out
    assert "can't evaluate  salesforce.update  (5 calls)   allow → error" in out


def test_demo_output_is_reproducible_and_redacted() -> None:
    a = _run("--salt", "0a").stdout
    b = _run("--salt", "0a").stdout

    assert a == b
    assert "ch_demo" not in a
    assert '"amount": "<int>"' in a
    assert '"amount": 750' in _run("--show-args", "amount").stdout


def test_demo_fail_on_none_exits_zero_and_quiet_hides_groups() -> None:
    result = _run("--fail-on", "none", "--quiet")

    assert result.exit_code == 0
    assert "exit 0 (nothing matched --fail-on none)" in result.stdout
    assert "demo-0178" not in result.stdout


def test_demo_rejects_unknown_engine() -> None:
    result = _run("--engine", "cedar")

    assert result.exit_code == 2
    assert "python" in result.stderr
