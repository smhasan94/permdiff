from __future__ import annotations

import hashlib
import io
import os
import platform
from collections.abc import Callable
from pathlib import Path
from typing import IO

import pytest
from click.testing import CliRunner

from permdiff.cli.main import cli
from permdiff.errors import EngineError
from permdiff.evaluators.opa import binary

FAKE_BIN = b"#!/bin/sh\necho fake opa\n"
FAKE_SHA = hashlib.sha256(FAKE_BIN).hexdigest()


class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _opener(payloads: dict[str, bytes]) -> Callable[[str], IO[bytes]]:
    def open_url(url: str) -> IO[bytes]:
        for suffix, body in payloads.items():
            if url.endswith(suffix):
                return _Response(body)
        raise OSError(f"no route to {url}")

    return open_url


@pytest.fixture
def asset() -> str:
    return binary.asset_for()


@pytest.fixture
def pinned_fake(monkeypatch: pytest.MonkeyPatch, asset: str) -> None:
    monkeypatch.setattr(binary, "OPA_SHA256", {binary.OPA_VERSION: {asset: FAKE_SHA}})


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(binary.ENV_CACHE, str(tmp_path / "cache"))
    monkeypatch.delenv(binary.ENV_BIN, raising=False)
    return tmp_path / "cache"


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Darwin", "arm64", "opa_darwin_arm64"),
        ("Darwin", "x86_64", "opa_darwin_amd64"),
        ("Linux", "x86_64", "opa_linux_amd64_static"),
        ("Linux", "aarch64", "opa_linux_arm64_static"),
        ("Windows", "AMD64", "opa_windows_amd64.exe"),
    ],
)
def test_asset_for_known_platforms(system: str, machine: str, expected: str) -> None:
    assert binary.asset_for(system, machine) == expected


def test_asset_for_unsupported_platform_names_overrides() -> None:
    with pytest.raises(EngineError, match="--opa-bin") as exc_info:
        binary.asset_for("Plan9", "mips")

    assert binary.ENV_BIN in str(exc_info.value)


def test_every_pinned_asset_has_a_checksum() -> None:
    pinned = binary.OPA_SHA256[binary.OPA_VERSION]

    assert set(binary.ASSETS.values()) == set(pinned)
    assert all(len(v) == 64 for v in pinned.values())


def test_cache_dir_precedence(tmp_path: Path) -> None:
    assert binary.cache_dir({binary.ENV_CACHE: str(tmp_path)}) == tmp_path
    if platform.system() != "Windows":
        assert binary.cache_dir({"XDG_CACHE_HOME": "/x"}) == Path("/x/permdiff")
        assert binary.cache_dir({}) == Path.home() / ".cache" / "permdiff"


def test_download_verifies_checksum_and_installs_executable(
    cache: Path, pinned_fake: None, asset: str, tmp_path: Path
) -> None:
    dest = tmp_path / "dest"

    path = binary.download(dest_dir=dest, opener=_opener({asset: FAKE_BIN}))

    assert path == dest / asset
    assert path.read_bytes() == FAKE_BIN
    assert os.access(path, os.X_OK)
    assert [p.name for p in dest.iterdir()] == [asset]


def test_download_rejects_checksum_mismatch_and_leaves_nothing(
    cache: Path, pinned_fake: None, asset: str, tmp_path: Path
) -> None:
    dest = tmp_path / "dest"

    with pytest.raises(EngineError, match="checksum mismatch"):
        binary.download(dest_dir=dest, opener=_opener({asset: b"tampered"}))

    assert list(dest.iterdir()) == []


def test_download_offline_names_the_overrides(
    cache: Path, pinned_fake: None, tmp_path: Path
) -> None:
    with pytest.raises(EngineError, match="Offline") as exc_info:
        binary.download(dest_dir=tmp_path, opener=_opener({}))

    assert "--opa-bin" in str(exc_info.value)


def test_unpinned_version_uses_release_sha256_sibling(
    cache: Path, asset: str, tmp_path: Path
) -> None:
    payloads = {f"{asset}.sha256": f"{FAKE_SHA}  {asset}\n".encode(), asset: FAKE_BIN}

    path = binary.download("9.9.9", tmp_path, opener=_opener(payloads))

    assert path.read_bytes() == FAKE_BIN


def test_resolve_prefers_explicit_then_env_then_cache_then_download(
    cache: Path, pinned_fake: None, asset: str, tmp_path: Path
) -> None:
    explicit = tmp_path / "explicit"
    explicit.write_bytes(FAKE_BIN)
    explicit.chmod(0o755)
    from_env = tmp_path / "from-env"
    from_env.write_bytes(FAKE_BIN)
    from_env.chmod(0o755)
    env = {binary.ENV_CACHE: str(cache), binary.ENV_BIN: str(from_env)}

    assert binary.resolve_binary(explicit, env=env) == explicit
    assert binary.resolve_binary(env=env) == from_env
    env_no_bin = {binary.ENV_CACHE: str(cache)}
    downloaded = binary.resolve_binary(env=env_no_bin, opener=_opener({asset: FAKE_BIN}))
    assert downloaded == cache / "opa" / binary.OPA_VERSION / asset
    assert binary.resolve_binary(env=env_no_bin, opener=_opener({})) == downloaded  # cached now


def test_resolve_explicit_missing_or_not_executable(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="--opa-bin"):
        binary.resolve_binary(tmp_path / "nope", env={})
    plain = tmp_path / "plain"
    plain.write_bytes(b"x")
    plain.chmod(0o644)
    with pytest.raises(EngineError, match="not executable"):
        binary.resolve_binary(plain, env={})


def test_resolve_env_path_missing_names_the_variable(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match=binary.ENV_BIN):
        binary.resolve_binary(env={binary.ENV_BIN: str(tmp_path / "gone")})


def test_resolve_without_download_names_setup_command(cache: Path) -> None:
    with pytest.raises(EngineError, match="permdiff setup opa"):
        binary.resolve_binary(env={binary.ENV_CACHE: str(cache)}, download_missing=False)


def test_setup_opa_command_downloads_then_reports_cached(
    cache: Path, pinned_fake: None, asset: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(binary, "_default_opener", _opener({asset: FAKE_BIN}))

    first = CliRunner().invoke(cli, ["setup", "opa"])
    second = CliRunner().invoke(cli, ["setup", "opa"])

    assert first.exit_code == 0, first.output
    assert "installed at" in first.stdout
    assert second.exit_code == 0
    assert "already installed" in second.stdout


def test_setup_opa_offline_is_an_engine_error(cache: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(binary, "_default_opener", _opener({}))

    result = CliRunner().invoke(cli, ["setup", "opa"])

    assert result.exit_code == 1
    assert "error: download failed" in result.stderr
