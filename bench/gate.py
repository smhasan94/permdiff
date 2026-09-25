"""Compare a benchmark result with the checked-in baseline; exit 1 on regression (NFR-P4)."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_RATIO = 1.5
TARGET_TOTAL_SECONDS = 60.0
TARGET_RSS_MB = 1024.0


def regressions(
    result: Mapping[str, Any], baseline: Mapping[str, Any], *, ratio: float = DEFAULT_RATIO
) -> list[str]:
    """Regressions: phases slower than ``ratio`` times the baseline, or targets missed."""
    problems = []
    for phase, seconds in result["phases"].items():
        reference = baseline.get("phases", {}).get(phase)
        if reference is not None and seconds > reference * ratio:
            problems.append(f"{phase}: {seconds:.2f}s > {ratio:.1f}x baseline {reference:.2f}s")
    if result["phases"].get("total", 0) > TARGET_TOTAL_SECONDS:
        problems.append(
            f"total {result['phases']['total']:.1f}s exceeds the {TARGET_TOTAL_SECONDS:.0f}s target"
        )
    if result.get("peak_rss_mb", 0) > TARGET_RSS_MB:
        problems.append(f"peak RSS {result['peak_rss_mb']:.0f} MB exceeds {TARGET_RSS_MB:.0f} MB")
    return problems


def select_baseline(
    baselines: Mapping[str, Any], platform_key: str, engine: str
) -> Mapping[str, Any] | None:
    entry = baselines.get(platform_key, {}).get(engine)
    return entry if isinstance(entry, Mapping) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--platform", required=True, help="Key in the baseline file, e.g. ci-linux")
    parser.add_argument("--ratio", type=float, default=DEFAULT_RATIO)
    args = parser.parse_args(argv)
    result = json.loads(args.result.read_text(encoding="utf-8"))
    baselines = json.loads(args.baseline.read_text(encoding="utf-8"))
    baseline = select_baseline(baselines, args.platform, result["engine"])
    if baseline is None:
        print(f"no baseline for {args.platform}/{result['engine']}; recording only")
        print(json.dumps(result["phases"]))
        return 0
    problems = regressions(result, baseline, ratio=args.ratio)
    for line in problems:
        print(f"REGRESSION {line}")
    if not problems:
        print(f"ok: {result['engine']} on {args.platform} within {args.ratio:.1f}x of baseline")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
