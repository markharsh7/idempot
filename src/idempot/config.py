# config — YAML loading, global Config singleton
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from idempot.exceptions import ConfigurationError

_DEFAULT_CONFIG: dict[str, Any] = {
    "backend": "memory",
    "default_ttl": 86400,
    "header_name": "Idempotency-Key",
    "lock_timeout": 5,
    "redis": {
        "url": "redis://localhost:6379",
        "key_prefix": "idempot:",
    },
    "cache_on_status": [200],
    "max_body_size": 10 * 1024 * 1024,  # 10 MB
}


class Config:
    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        merged: dict[str, Any] = dict(_DEFAULT_CONFIG)
        if settings:
            for key, value in settings.items():
                if key == "redis" and isinstance(value, dict):
                    merged_redis: dict[str, Any] = dict(_DEFAULT_CONFIG["redis"])
                    merged_redis.update(value)
                    merged["redis"] = merged_redis
                else:
                    merged[key] = value

        self.backend: str = merged["backend"]
        self.default_ttl: int = merged["default_ttl"]
        self.header_name: str = merged["header_name"]
        self.lock_timeout: int = merged["lock_timeout"]
        redis_cfg: dict[str, Any] = merged["redis"]
        self.redis_url: str = redis_cfg["url"]
        self.redis_key_prefix: str = redis_cfg["key_prefix"]
        self.cache_on_status: list[int] = merged["cache_on_status"]
        self.max_body_size: int = merged["max_body_size"]

    @classmethod
    def from_yaml(cls, path: str | Path) -> Config:
        path = Path(path)
        if not path.exists():
            raise ConfigurationError(f"Config file not found: {path}")
        with open(path, "r") as f:
            data: Any = yaml.safe_load(f) or {}
        return cls(data)

    @classmethod
    def from_kwargs(cls, **kwargs: Any) -> Config:
        settings: dict[str, Any] = {}
        flat_keys = {
            "backend", "default_ttl", "header_name", "lock_timeout",
            "cache_on_status", "max_body_size",
        }
        redis_keys: dict[str, Any] = {}
        for k, v in kwargs.items():
            if k in flat_keys:
                settings[k] = v
            elif k.startswith("redis_"):
                redis_keys[k[6:]] = v
        if redis_keys:
            settings["redis"] = redis_keys
        return cls(settings)


_config: Config | None = None


def configure(
    config_path: str | Path | None = None,
    **kwargs: Any,
) -> Config:
    global _config

    if config_path:
        _config = Config.from_yaml(config_path)
    elif kwargs:
        _config = Config.from_kwargs(**kwargs)
    else:
        _config = Config()

    return _config


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
