from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(RuntimeError):
    """Raised for invalid configuration values."""


@dataclass(slots=True)
class AppConfig:
    base_url: str | None = None
    token: str | None = None
    email: str | None = None
    password: str | None = None
    timeout: float | None = None


def config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "fairsharing-cli" / "config.json"


def load_config(path: Path | None = None) -> AppConfig:
    cfg_path = path or config_path()
    if not cfg_path.exists():
        return AppConfig()
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid config JSON in {cfg_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Invalid config structure in {cfg_path}: expected JSON object")
    timeout: float | None = None
    if "timeout" in data and data["timeout"] is not None:
        try:
            timeout = float(data["timeout"])
        except (TypeError, ValueError) as exc:
            raise ConfigError("Config field 'timeout' must be numeric") from exc
    return AppConfig(
        base_url=_optional_string(data, "base_url"),
        token=_optional_string(data, "token"),
        email=_optional_string(data, "email"),
        password=_optional_string(data, "password"),
        timeout=timeout,
    )


def save_config(config: AppConfig, path: Path | None = None) -> None:
    cfg_path = path or config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "base_url": config.base_url,
        "token": config.token,
        "email": config.email,
        "password": config.password,
        "timeout": config.timeout,
    }
    cfg_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


@dataclass(slots=True)
class ResolvedSettings:
    base_url: str
    token: str | None
    email: str | None
    password: str | None
    timeout: float


def resolve_settings(
    *,
    cli_base_url: str | None,
    cli_token: str | None,
    cli_email: str | None,
    cli_password: str | None,
    cli_timeout: float | None,
    config: AppConfig,
) -> ResolvedSettings:
    base_url = (
        cli_base_url
        or os.environ.get("FAIRSHARING_BASE_URL")
        or config.base_url
        or "https://api.fairsharing.org"
    )
    token = cli_token or os.environ.get("FAIRSHARING_TOKEN") or config.token
    email = cli_email or os.environ.get("FAIRSHARING_EMAIL") or config.email
    password = cli_password or os.environ.get("FAIRSHARING_PASSWORD") or config.password

    timeout = cli_timeout
    if timeout is None and os.environ.get("FAIRSHARING_TIMEOUT") is not None:
        try:
            timeout = float(os.environ["FAIRSHARING_TIMEOUT"])
        except ValueError as exc:
            raise ConfigError("Environment FAIRSHARING_TIMEOUT must be numeric") from exc
    if timeout is None:
        timeout = config.timeout
    if timeout is None:
        timeout = 30.0
    if timeout <= 0:
        raise ConfigError("Timeout must be greater than zero")
    return ResolvedSettings(
        base_url=base_url,
        token=token,
        email=email,
        password=password,
        timeout=timeout,
    )


def _optional_string(mapping: dict[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"Config field '{key}' must be a string")
    return value
