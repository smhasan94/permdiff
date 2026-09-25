from __future__ import annotations

from pathlib import Path

import pytest

from permdiff.config import Config, find_config, load_config, render_toml
from permdiff.config.load import ENV_CONFIG, env_overrides
from permdiff.errors import ConfigError


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_when_nothing_is_configured(tmp_path: Path) -> None:
    cfg = load_config(tmp_path, env={})

    assert cfg == Config()
    assert cfg.policy.engine == "opa"
    assert cfg.report.fail_on == "widen"
    assert cfg.traces.paths == ()


def test_precedence_flags_over_env_over_file_over_defaults(tmp_path: Path) -> None:
    _write(
        tmp_path / "permdiff.toml",
        '[policy]\nengine = "python:x:y"\nbase = "v1"\n[report]\nsamples = 5\nfail_on = "none"\n',
    )
    env = {"PERMDIFF_POLICY_BASE": "v2", "PERMDIFF_REPORT_SAMPLES": "7"}

    cfg = load_config(tmp_path, env=env, overrides={"policy": {"base": "v3"}})

    assert cfg.policy.engine == "python:x:y"  # file
    assert cfg.policy.base == "v3"  # flag beats env beats file
    assert cfg.report.samples == 7  # env beats file
    assert cfg.report.fail_on == "none"  # file beats default
    assert cfg.policy.head == "HEAD"  # default


def test_env_parsing_by_field_type() -> None:
    env = {
        "PERMDIFF_TRACES_STRICT": "yes",
        "PERMDIFF_OPA_V0_COMPATIBLE": "0",
        "PERMDIFF_REPORT_GROUP_BY": "tool, agent",
        "PERMDIFF_TRACES_PATHS": "a.jsonl,b/*.jsonl",
        "PERMDIFF_TRACES_SINCE": "",
        "PERMDIFF_REPORT_MAX_GROUPS": "12",
        "UNRELATED": "x",
    }

    assert env_overrides(env) == {
        "traces": {"strict": True, "paths": ("a.jsonl", "b/*.jsonl"), "since": None},
        "opa": {"v0_compatible": False},
        "report": {"group_by": ("tool", "agent"), "max_groups": 12},
    }


@pytest.mark.parametrize(
    ("name", "value", "fragment"),
    [
        ("PERMDIFF_TRACES_STRICT", "maybe", "true/false"),
        ("PERMDIFF_REPORT_SAMPLES", "three", "integer"),
        ("PERMDIFF_REPORT_FAIL_ON", "sometimes", "report.fail_on"),
    ],
)
def test_bad_env_values_name_the_variable_or_key(
    name: str, value: str, fragment: str, tmp_path: Path
) -> None:
    with pytest.raises(ConfigError, match=fragment):
        load_config(tmp_path, env={name: value})


def test_unknown_keys_and_sections_are_errors(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    _write(tmp_path / "a" / "permdiff.toml", "[report]\nsampels = 3\n")
    with pytest.raises(ConfigError, match=r"unknown key report\.sampels"):
        load_config(tmp_path / "a", env={})

    (tmp_path / "b").mkdir()
    _write(tmp_path / "b" / "permdiff.toml", "[reports]\nsamples = 3\n")
    with pytest.raises(ConfigError, match=r"unknown section \[reports\]"):
        load_config(tmp_path / "b", env={})


def test_invalid_toml_and_bad_values_are_config_errors(tmp_path: Path) -> None:
    _write(tmp_path / "permdiff.toml", "[report\n")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(tmp_path, env={})

    _write(tmp_path / "permdiff.toml", '[report]\nredact = "sometimes"\n')
    with pytest.raises(ConfigError, match=r"report\.redact"):
        load_config(tmp_path, env={})


def test_discovery_walks_up_and_stops_at_the_repo_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sub = repo / "services" / "api"
    sub.mkdir(parents=True)
    _write(tmp_path / "permdiff.toml", '[policy]\nengine = "python:outside:x"\n')

    assert find_config(sub, stop_at=repo) is None
    assert find_config(sub) == tmp_path / "permdiff.toml"

    _write(repo / "permdiff.toml", '[policy]\nengine = "python:inside:x"\n')
    assert load_config(sub, env={}, stop_at=repo).policy.engine == "python:inside:x"


def test_explicit_path_and_env_config_beat_discovery(tmp_path: Path) -> None:
    _write(tmp_path / "permdiff.toml", "[report]\nsamples = 1\n")
    other = _write(tmp_path / "other.toml", "[report]\nsamples = 2\n")
    third = _write(tmp_path / "third.toml", "[report]\nsamples = 3\n")

    assert load_config(tmp_path, env={}).report.samples == 1
    assert load_config(tmp_path, env={ENV_CONFIG: str(other)}).report.samples == 2
    assert load_config(tmp_path, env={ENV_CONFIG: str(other)}, explicit=third).report.samples == 3
    with pytest.raises(ConfigError, match="config file not found"):
        load_config(tmp_path, env={}, explicit=tmp_path / "missing.toml")


def test_render_toml_round_trips_through_the_loader(tmp_path: Path) -> None:
    cfg = Config.model_validate(
        {"policy": {"engine": "python:a:b"}, "traces": {"paths": ["t/*.jsonl"], "since": "7d"}}
    )
    path = _write(tmp_path / "permdiff.toml", render_toml(cfg))

    assert load_config(tmp_path, env={}) == cfg
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# permdiff configuration")
    assert 'engine = "python:a:b"  # opa | cedar' in text
    assert "[cedar]" in text
