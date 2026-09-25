"""Pinned ``opa`` binary: locate, download over HTTPS, verify SHA-256 (AC-10.1, NFR-S3).

Resolution order: ``--opa-bin`` > ``PERMDIFF_OPA_BIN`` > user cache > download.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import shutil
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import IO, Final
from urllib.error import URLError
from urllib.request import Request, urlopen

from permdiff.errors import EngineError

log = logging.getLogger(__name__)

OPA_VERSION: Final = "1.21.0"
RELEASE_URL: Final = "https://github.com/open-policy-agent/opa/releases/download/v{version}/{asset}"
ENV_BIN: Final = "PERMDIFF_OPA_BIN"
ENV_CACHE: Final = "PERMDIFF_CACHE_DIR"
DOWNLOAD_TIMEOUT: Final = 120.0
_CHUNK: Final = 1 << 20

ASSETS: Final[Mapping[tuple[str, str], str]] = {
    ("darwin", "arm64"): "opa_darwin_arm64",
    ("darwin", "x86_64"): "opa_darwin_amd64",
    ("linux", "x86_64"): "opa_linux_amd64_static",
    ("linux", "aarch64"): "opa_linux_arm64_static",
    ("linux", "arm64"): "opa_linux_arm64_static",
    ("windows", "amd64"): "opa_windows_amd64.exe",
    ("windows", "x86_64"): "opa_windows_amd64.exe",
}

# Fetched 2026-09-25 from the release's *.sha256 assets.
_SHA_1_21_0: Final[Mapping[str, str]] = {
    "opa_darwin_amd64": "0ceb96979d259b3ee31711a6b316a592b8ffcfdd4209cc37600ed85a6cd4a55c",
    "opa_darwin_arm64": "f1e4da6467a2adb2846bb23eec6ea00d8c3a04786f9270bb11003d22dfd827a5",
    "opa_linux_amd64_static": "5eef70644868bb04d0556bcc795ee42f2ab379e73f51d1bfa30f83e1305bc9b9",
    "opa_linux_arm64_static": "0ec34027c15b4d969c21d01ed570fe14fbebd508a08157043ab09f9a0dccbee6",
    "opa_windows_amd64.exe": "1e0e9639673615fa3a6d4974b07e335e44827e377ce7c7bffbb1a6605a26479b",
}

OPA_SHA256: Final[Mapping[str, Mapping[str, str]]] = {"1.21.0": _SHA_1_21_0}

Opener = Callable[[str], IO[bytes]]


def _default_opener(url: str) -> IO[bytes]:
    request = Request(url, headers={"User-Agent": "permdiff"})  # noqa: S310  # https only, fixed host
    response: IO[bytes] = urlopen(request, timeout=DOWNLOAD_TIMEOUT)  # noqa: S310
    return response


def _opener_or_default(opener: Opener | None) -> Opener:
    return opener if opener is not None else _default_opener


def asset_for(system: str | None = None, machine: str | None = None) -> str:
    """Release asset name for this platform, or ``EngineError`` when unsupported."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    try:
        return ASSETS[(system, machine)]
    except KeyError:
        supported = ", ".join(f"{s}/{m}" for s, m in ASSETS)
        msg = (
            f"no pinned opa binary for {system}/{machine}; supported: {supported}. "
            f"Install opa yourself and pass --opa-bin or set {ENV_BIN}"
        )
        raise EngineError(msg) from None


def cache_dir(env: Mapping[str, str] | None = None) -> Path:
    """``$PERMDIFF_CACHE_DIR``, else the platform user cache, under ``permdiff``."""
    env = os.environ if env is None else env
    if explicit := env.get(ENV_CACHE):
        return Path(explicit)
    if platform.system() == "Windows":
        base = Path(env.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif xdg := env.get("XDG_CACHE_HOME"):
        base = Path(xdg)
    else:
        base = Path.home() / ".cache"
    return base / "permdiff"


def cached_path(version: str = OPA_VERSION, env: Mapping[str, str] | None = None) -> Path:
    return cache_dir(env) / "opa" / version / asset_for()


def _read_all(opener: Opener, url: str) -> bytes:
    try:
        with opener(url) as response:
            return response.read()
    except (URLError, OSError) as exc:
        msg = f"download failed for {url}: {exc}. Offline? Pass --opa-bin or set {ENV_BIN}"
        raise EngineError(msg) from exc


def expected_sha256(version: str, asset: str, *, opener: Opener | None = None) -> str:
    """Pinned checksum, or for other versions the release's ``.sha256`` sibling (same origin)."""
    pinned = OPA_SHA256.get(version, {}).get(asset)
    if pinned:
        return pinned
    log.warning("opa %s is not pinned; trusting the release's .sha256 asset", version)
    text = _read_all(
        _opener_or_default(opener), RELEASE_URL.format(version=version, asset=f"{asset}.sha256")
    )
    return text.decode("ascii", "replace").split()[0].lower()


def download(
    version: str = OPA_VERSION, dest_dir: Path | None = None, *, opener: Opener | None = None
) -> Path:
    """Fetch the binary for this platform into ``dest_dir`` with checksum verification."""
    opener = _opener_or_default(opener)
    asset = asset_for()
    dest_dir = dest_dir if dest_dir is not None else cached_path(version).parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / asset
    expected = expected_sha256(version, asset, opener=opener)
    url = RELEASE_URL.format(version=version, asset=asset)
    log.info("downloading %s", url)
    digest = hashlib.sha256()
    fd, tmp_name = tempfile.mkstemp(prefix=f".{asset}.", dir=dest_dir)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out, _open_or_raise(opener, url) as response:
            while chunk := response.read(_CHUNK):
                digest.update(chunk)
                out.write(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            msg = (
                f"checksum mismatch for {asset} {version}: expected {expected}, got {actual}; "
                "refusing to install"
            )
            raise EngineError(msg)
        tmp.chmod(0o755)
        tmp.replace(final)
    finally:
        tmp.unlink(missing_ok=True)
    log.info("installed opa %s at %s", version, final)
    return final


def _open_or_raise(opener: Opener, url: str) -> IO[bytes]:
    try:
        return opener(url)
    except (URLError, OSError) as exc:
        msg = f"download failed for {url}: {exc}. Offline? Pass --opa-bin or set {ENV_BIN}"
        raise EngineError(msg) from exc


def _check_executable(path: Path, *, source: str) -> Path:
    if not path.is_file():
        msg = f"opa binary from {source} does not exist: {path}"
        raise EngineError(msg)
    if not os.access(path, os.X_OK):
        msg = f"opa binary from {source} is not executable: {path}"
        raise EngineError(msg)
    return path


def resolve_binary(
    explicit: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    download_missing: bool = True,
    version: str = OPA_VERSION,
    opener: Opener | None = None,
) -> Path:
    """The ``opa`` executable to use; see the module docstring for precedence."""
    env = os.environ if env is None else env
    if explicit is not None:
        return _check_executable(explicit, source="--opa-bin")
    if from_env := env.get(ENV_BIN):
        return _check_executable(Path(from_env), source=ENV_BIN)
    cached = cached_path(version, env)
    if cached.is_file():
        return cached
    if not download_missing:
        msg = (
            f"opa {version} is not installed (looked in {cached}); run `permdiff setup opa`, "
            f"pass --opa-bin, or set {ENV_BIN}"
        )
        raise EngineError(msg)
    if shutil.which("opa") and log.isEnabledFor(logging.INFO):
        log.info(
            "ignoring opa on PATH; permdiff uses its pinned %s (override with --opa-bin)", version
        )
    return download(version, cached.parent, opener=opener)
