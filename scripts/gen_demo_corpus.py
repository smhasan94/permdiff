"""Regenerate ``src/permdiff/demo/corpus.jsonl`` deterministically.

Synthetic data only: no names, emails, or real identifiers. A test asserts the
checked-in file equals this script's output, so edit the generator, not the file.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

SEED = 42
START = datetime(2026, 9, 18, 8, 0, tzinfo=UTC)
OUT = Path(__file__).resolve().parents[1] / "src" / "permdiff" / "demo" / "corpus.jsonl"

# (tool, count, argument factory)
PLAN: tuple[tuple[str, int], ...] = (
    ("github.read", 90),
    ("slack.post", 40),
    ("stripe.refund", 30),
    ("aws.ec2.terminate_instance", 15),
    ("github.delete_branch", 10),
    ("salesforce.update", 15),
)
TEAMS = ("support", "ops", "finance", "sales")
DEPARTMENTS = ("cs", "eng", "fin")
ENVS = ("prod", "staging", "dev")
AGENTS = ("support-bot", "ops-bot", "finance-bot")


def _arguments(rng: random.Random, tool: str, i: int) -> dict[str, object]:
    if tool == "github.read":
        return {"repo": f"org/repo-{rng.randint(1, 12)}", "path": f"docs/file-{i}.md"}
    if tool == "slack.post":
        return {"channel": f"#team-{rng.choice(TEAMS)}", "text_len": rng.randint(20, 400)}
    if tool == "stripe.refund":
        amount = rng.choice([60, 120, 240, 480, 520, 750, 900, 1250, 1800])
        return {"charge_id": f"ch_demo{i:04d}", "amount": amount, "currency": "usd"}
    if tool == "aws.ec2.terminate_instance":
        return {"instance_id": f"i-0demo{i:04x}", "region": rng.choice(["us-east-1", "eu-west-1"])}
    if tool == "github.delete_branch":
        return {"repo": f"org/repo-{rng.randint(1, 12)}", "branch": f"feature/demo-{i}"}
    return {"object": "Opportunity", "id": f"006demo{i:05d}", "fields": {"stage": "closed"}}


def _principal(rng: random.Random, tool: str, i: int) -> dict[str, object]:
    team = "ops" if tool == "aws.ec2.terminate_instance" else rng.choice(TEAMS)
    attrs: dict[str, object] = {"team": team}
    # Some Salesforce callers lack a department: head's policy needs it → can't evaluate.
    if tool != "salesforce.update" or i % 3 != 0:
        attrs["department"] = rng.choice(DEPARTMENTS)
    return {"id": f"{team}-agent-{rng.randint(1, 9):02d}", "type": "user", "attrs": attrs}


def generate() -> list[dict[str, object]]:
    rng = random.Random(SEED)  # noqa: S311  # synthetic fixture data, not security
    records: list[dict[str, object]] = []
    n = 0
    for tool, count in PLAN:
        for i in range(count):
            n += 1
            env = "prod" if tool != "github.delete_branch" or i % 5 < 2 else rng.choice(ENVS[1:])
            records.append(
                {
                    "id": f"demo-{n:04d}",
                    "timestamp": (START + timedelta(minutes=n * 47)).isoformat(),
                    "principal": _principal(rng, tool, i),
                    "agent": {"id": rng.choice(AGENTS), "version": "1.4.0"},
                    "tool": {"name": tool, "server": tool.split(".")[0] + "-mcp"},
                    "arguments": _arguments(rng, tool, i),
                    "resource": {"type": tool.rsplit(".", 1)[0]},
                    "context": {"session_id": f"sess-{n // 7:03d}", "env": env},
                }
            )
    records.sort(key=lambda r: str(r["timestamp"]))
    return records


def render() -> str:
    return "".join(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n" for r in generate())


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT} ({len(generate())} records)")
