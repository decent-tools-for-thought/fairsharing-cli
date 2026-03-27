from __future__ import annotations

from pathlib import Path

import pytest

from fairsharing_cli.config import (
    AppConfig,
    ConfigError,
    load_config,
    resolve_settings,
    save_config,
)


def test_load_save_config_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    cfg = AppConfig(base_url="https://x", token="t", email="e", password="p", timeout=9.0)
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded == cfg


def test_load_config_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_resolve_settings_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAIRSHARING_BASE_URL", "https://env")
    monkeypatch.setenv("FAIRSHARING_TOKEN", "envtoken")
    cfg = AppConfig(base_url="https://cfg", token="cfgtoken", timeout=15.0)
    resolved = resolve_settings(
        cli_base_url="https://cli",
        cli_token="clitoken",
        cli_email=None,
        cli_password=None,
        cli_timeout=20.0,
        config=cfg,
    )
    assert resolved.base_url == "https://cli"
    assert resolved.token == "clitoken"
    assert resolved.timeout == 20.0


def test_resolve_settings_env_timeout_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAIRSHARING_TIMEOUT", "abc")
    with pytest.raises(ConfigError):
        resolve_settings(
            cli_base_url=None,
            cli_token=None,
            cli_email=None,
            cli_password=None,
            cli_timeout=None,
            config=AppConfig(),
        )
