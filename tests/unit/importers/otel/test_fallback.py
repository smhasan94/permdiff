from __future__ import annotations

from permdiff.importers.otel import OtelImporter
from permdiff.importers.otel.mapping import normalize
from tests.conftest import OPA_FIXTURES

FIXTURE = OPA_FIXTURES.parent / "otel" / "parent_fallback.json"


def _calls() -> dict[str, object]:
    result = OtelImporter().read(FIXTURE)
    return {c.tool.name: c for c in result.calls}


def test_arguments_come_from_the_parent_tool_call_part_by_id() -> None:
    calls = _calls()

    refund = calls["stripe.refund"]
    assert refund.arguments == {"charge_id": "ch_A", "amount": 900}  # type: ignore[attr-defined]


def test_deprecated_gen_ai_system_is_an_alias_for_provider_name() -> None:
    assert normalize({"gen_ai.system": "openai"})["gen_ai.provider.name"] == "openai"
    both = normalize({"gen_ai.system": "old", "gen_ai.provider.name": "new"})
    assert both["gen_ai.provider.name"] == "new"


def test_unique_name_match_when_the_span_has_no_call_id() -> None:
    assert _calls()["slack.post"].arguments == {"channel": "#ops"}  # type: ignore[attr-defined]


def test_no_match_leaves_arguments_absent() -> None:
    assert _calls()["weather"].arguments is None  # type: ignore[attr-defined]


def test_deprecated_gen_ai_choice_event_is_read() -> None:
    assert _calls()["github.read"].arguments == {"repo": "org/legacy"}  # type: ignore[attr-defined]


def test_mcp_tools_call_spans_are_imported_and_nameless_ones_skipped() -> None:
    result = OtelImporter().read(FIXTURE)
    flights = next(c for c in result.calls if c.tool.name == "Flights")

    assert flights.tool.server == "mcp"
    assert flights.arguments == {"from": "SFO", "to": "JFK"}
    assert flights.context["mcp.session_id"] == "mcp-sess-1"
    assert flights.principal.id == "carol"  # resource user.id
    assert result.stats.skipped == 1
    assert "no tool" in result.stats.skipped_locators[0]


def test_lookup_walks_several_ancestors() -> None:
    assert _calls()["deep"].arguments == {"level": 2}  # type: ignore[attr-defined]
    assert _calls()["deep"].agent.id == "support-bot"  # type: ignore[attr-defined]
