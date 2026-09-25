"""Generate a synthetic corpus shaped like the demo corpus, at any size, deterministically."""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

TOOLS = (
    ("github.read", 45),
    ("slack.post", 20),
    ("stripe.refund", 15),
    ("aws.ec2.terminate_instance", 8),
    ("github.delete_branch", 5),
    ("salesforce.update", 7),
)
TEAMS = ("support", "ops", "finance", "sales")
DEPARTMENTS = ("cs", "eng", "fin")
START = datetime(2026, 9, 1, tzinfo=UTC)


def _pick_tool(rng: random.Random) -> str:
    total = sum(w for _, w in TOOLS)
    point = rng.randrange(total)
    for name, weight in TOOLS:
        if point < weight:
            return name
        point -= weight
    return TOOLS[0][0]


def records(n: int, seed: int = 7) -> Iterator[dict[str, object]]:
    rng = random.Random(seed)  # noqa: S311  # synthetic data
    for i in range(n):
        tool = _pick_tool(rng)
        team = "ops" if tool == "aws.ec2.terminate_instance" else rng.choice(TEAMS)
        attrs: dict[str, object] = {"team": team}
        if not (tool == "salesforce.update" and i % 3 == 0):
            attrs["department"] = rng.choice(DEPARTMENTS)
        args: dict[str, object] = {"n": i, "note": "x" * 32}
        if tool == "stripe.refund":
            args["amount"] = rng.choice([60, 240, 480, 520, 900, 1800])
        yield {
            "id": f"bench-{i:07d}",
            "timestamp": (START + timedelta(seconds=i * 13)).isoformat(),
            "principal": {
                "id": f"{team}-agent-{rng.randint(1, 40):02d}",
                "type": "user",
                "attrs": attrs,
            },
            "agent": {"id": rng.choice(("support-bot", "ops-bot")), "version": "1.4.0"},
            "tool": {"name": tool, "server": tool.split(".")[0] + "-mcp"},
            "arguments": args,
            "resource": {"type": tool.rsplit(".", 1)[0], "id": f"res-{i % 500}"},
            "context": {
                "session_id": f"sess-{i // 9:05d}",
                "env": rng.choice(("prod", "prod", "staging")),
            },
        }


def write(path: Path, n: int, seed: int = 7) -> int:
    with path.open("w", encoding="utf-8") as fh:
        for record in records(n, seed):
            fh.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    write(args.out, args.n, args.seed)
    print(f"wrote {args.n} records to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
