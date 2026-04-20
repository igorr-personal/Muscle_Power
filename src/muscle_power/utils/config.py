"""Configuration loading and validation for Muscle Power."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from muscle_power.utils.errors import ConfigError
from muscle_power.utils.logger import get_logger

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------


class CacheConfig(BaseModel):
    ttl_minutes: int = Field(60, ge=1)
    max_size_mb: int = Field(500, ge=1)


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///muscle_power.db"


class SensorConfig(BaseModel):
    preferred_address: str = ""
    sampling_frequency: int = Field(250, description="Hz")
    signal_type: str = "EMG"
    display_window_seconds: int = Field(5, ge=1, le=30)
    rms_window_ms: int = Field(200, ge=50)
    battery_warn_pct: int = Field(20, ge=5)
    battery_alert_pct: int = Field(10, ge=1)
    battery_autosave_pct: int = Field(5, ge=1)


class SessionConfig(BaseModel):
    min_duration_seconds: int = Field(30, ge=5)


class KBConfig(BaseModel):
    enabled: bool = False
    documents_dir: str = "documents"
    index_dir: str = "kb_data"
    embedding_model: str = "all-mpnet-base-v2"
    top_k: int = 5


class AppConfig(BaseModel):
    env: str = "development"
    log_level: str = "INFO"
    debug: bool = False
    cache: CacheConfig = Field(default_factory=CacheConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    sensor: SensorConfig = Field(default_factory=SensorConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    kb: KBConfig = Field(default_factory=KBConfig)

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return v.upper()


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _load_env() -> None:
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv(Path(".env.example"), override=False)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Configuration file is invalid: {exc}") from exc


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """Load config from YAML + environment variable overrides."""
    _load_env()
    raw = _load_yaml(Path(config_path))

    # env var overrides
    if db_url := os.getenv("DATABASE_URL"):
        raw.setdefault("database", {})["url"] = db_url
    if log_level := os.getenv("LOG_LEVEL"):
        raw["log_level"] = log_level
    if app_env := os.getenv("APP_ENV"):
        raw["env"] = app_env
    if debug := os.getenv("DEBUG"):
        raw["debug"] = debug.lower() in ("1", "true", "yes")
    if addr := os.getenv("PREFERRED_SENSOR_ADDRESS"):
        raw.setdefault("sensor", {})["preferred_address"] = addr

    try:
        cfg = AppConfig(**raw)
        _log.info(
            "Configuration loaded",
            extra={"action": "config_load", "details": {"env": cfg.env, "log_level": cfg.log_level}},
        )
        return cfg
    except Exception as exc:
        raise ConfigError(f"Invalid configuration: {exc}") from exc


_config: AppConfig | None = None


def get_config() -> AppConfig:
    global _config
    if _config is None:
        try:
            _config = load_config()
        except ConfigError:
            _config = AppConfig()
    return _config


def reset_config() -> None:
    """Force config reload (useful after settings change)."""
    global _config
    _config = None
