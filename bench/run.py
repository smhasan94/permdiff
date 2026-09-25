"""End-to-end timing per phase for one engine; prints a JSON result (NFR-P1, NFR-P2)."""

from __future__ import annotations

import argparse
import json
import platform
import resource
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from bench.generate import write
from permdiff import api, demo
from permdiff.policy import DirectorySource
from permdiff.redact import Redactor
from permdiff.report import FailOn, build_view, gate, render_markdown

ENGINES = ("python", "opa", "cedar")


def _engine(name: str, opa_bin: Path | None) -> tuple[str, dict[str, Any]]:
    if name == "python":
        return demo.ENGINE_SPEC, {}
    if name == "cedar":
        return "cedar", {"resource": demo.CEDAR_RESOURCE}
    options: dict[str, Any] = {"decision": demo.OPA_DECISION}
    if opa_bin is not None:
        options["opa_bin"] = opa_bin
    return "opa", options


def _peak_rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage / (1024 * 1024) if sys.platform == "darwin" else usage / 1024


def run(
    engine: str, n: int, *, opa_bin: Path | None = None, corpus: Path | None = None
) -> dict[str, Any]:
    phases: dict[str, float] = {}
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="permdiff-bench-") as tmp:
        path = corpus if corpus is not None else Path(tmp) / "corpus.jsonl"
        if corpus is None:
            write(path, n)
        t = time.perf_counter()
        imported = api.load_traces([path], fmt="jsonl")
        phases["import"] = time.perf_counter() - t
        spec, options = _engine(engine, opa_bin)
        t = time.perf_counter()
        report = api.diff_sources(
            traces=imported.calls,
            base=DirectorySource(demo.POLICY_BASE, demo.BASE_LABEL),
            head=DirectorySource(demo.POLICY_HEAD, demo.HEAD_LABEL),
            policy_path="demo/policy",
            engine=spec,
            engine_options=options,
            salt=bytes(16),
            import_stats=imported.stats,
        )
        phases["diff"] = time.perf_counter() - t
        t = time.perf_counter()
        view = build_view(report, redactor=Redactor(salt=bytes(16)))
        markdown = render_markdown(view, exit_code=gate(view, FailOn.WIDEN), fail_on=FailOn.WIDEN)
        phases["report"] = time.perf_counter() - t
    phases["total"] = time.perf_counter() - started
    return {
        "engine": engine,
        "n": len(imported.calls),
        "platform": f"{platform.system().lower()}-{platform.machine().lower()}",
        "python": platform.python_version(),
        "phases": {k: round(v, 3) for k, v in phases.items()},
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "markdown_bytes": len(markdown.encode("utf-8")),
        "counts": report.counts.model_dump(mode="json"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=ENGINES, default="python")
    parser.add_argument("--n", type=int, default=100_000)
    parser.add_argument("--opa-bin", type=Path, default=None)
    parser.add_argument(
        "--corpus", type=Path, default=None, help="Existing JSONL instead of generating."
    )
    parser.add_argument("--out", type=Path, default=None, help="Write the JSON result here too.")
    args = parser.parse_args(argv)
    result = run(args.engine, args.n, opa_bin=args.opa_bin, corpus=args.corpus)
    text = json.dumps(result, indent=2)
    print(text)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
