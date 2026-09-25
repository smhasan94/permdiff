"""Restricted OPA capabilities: the pinned binary's builtins minus the nondeterministic ones.

A policy that calls a denied builtin fails ``opa check`` with ``undefined function
<name>``; the evaluator turns that into ``error/nondeterministic`` for every call
(AC-10.6). ``--nd-cache`` re-allows the builtins it has recorded values for.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from functools import cache
from pathlib import Path
from typing import Any, Final

from permdiff import _proc
from permdiff.errors import EngineError
from permdiff.evaluators.opa.binary import cache_dir

DENIED_BUILTINS: Final[tuple[str, ...]] = (
    "http.send",
    "net.lookup_ip_addr",
    "rand.intn",
    "uuid.rfc4122",
    "opa.runtime",
)


@cache
def load_capabilities(opa_bin: Path) -> dict[str, Any]:
    """``opa capabilities --current`` for this binary, parsed once per process."""
    result = _proc.run([opa_bin, "capabilities", "--current"])
    if not result.ok:
        msg = f"opa capabilities failed ({opa_bin}): {result.stderr.strip()[:300]}"
        raise EngineError(msg)
    try:
        caps: dict[str, Any] = json.loads(result.stdout)
    except ValueError as exc:
        msg = f"opa capabilities returned invalid JSON ({opa_bin})"
        raise EngineError(msg) from exc
    return caps


def builtin_arity(opa_bin: Path, name: str) -> int:
    """Number of arguments ``name`` takes, from the capabilities declaration."""
    for builtin in load_capabilities(opa_bin).get("builtins", []):
        if builtin.get("name") == name:
            args = builtin.get("decl", {}).get("args", [])
            return len(args)
    msg = f"builtin {name!r} is unknown to this opa binary; check the --nd-cache file"
    raise EngineError(msg)


def restricted_capabilities(
    opa_bin: Path,
    *,
    allow: Iterable[str] = (),
    denied: Iterable[str] = DENIED_BUILTINS,
    cache_root: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Write (once) and return the capabilities file with ``denied`` minus ``allow`` removed."""
    removed = set(denied) - set(allow)
    caps = dict(load_capabilities(opa_bin))
    caps["builtins"] = [b for b in caps.get("builtins", []) if b.get("name") not in removed]
    text = json.dumps(caps, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    root = cache_root if cache_root is not None else cache_dir(env)
    path = root / "opa" / "capabilities" / f"{digest}.json"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    return path
