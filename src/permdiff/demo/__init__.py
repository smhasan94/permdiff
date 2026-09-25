"""Bundled demo: two policy versions and a synthetic 200-call corpus (FR-24)."""

from __future__ import annotations

from pathlib import Path

DEMO_DIR = Path(__file__).parent
CORPUS = DEMO_DIR / "corpus.jsonl"
POLICY_BASE = DEMO_DIR / "policy_base"
POLICY_HEAD = DEMO_DIR / "policy_head"
BASE_LABEL = "demo/base"
HEAD_LABEL = "demo/head"
ENGINE_SPEC = "python:permdiff.demo.engine:evaluate"
OPA_DECISION = "data.agent.authz.decision"
CEDAR_RESOURCE = 'Resource::"{resource.type}"'
