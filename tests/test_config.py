# tests for config layer
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from idempot.config import Config, configure, get_config
from idempot.exceptions import ConfigurationError


class TestConfigDefaults:
    def test_default_backend_is_memory(self) -> None:
        c = Config()
        assert c.backend == "memory"

    def test_default_ttl(self) -> None:
        c = Config()
        assert c.default_ttl == 86400

    def test_default_header_name(self) -> None:
        c = Config()
        assert c.header_name == "Idempotency-Key"

    def test_default_lock_timeout(self) -> None:
        c = Config()
        assert c.lock_timeout == 5

    def test_default_redis_url(self) -> None:
        c = Config()
        assert c.redis_url == "redis://localhost:6379"

    def test_default_redis_key_prefix(self) -> None:
        c = Config()
        assert c.redis_key_prefix == "idempot:"

    def test_default_cache_on_status(self) -> None:
        c = Config()
        assert c.cache_on_status == [200]

    def test_default_max_body_size(self) -> None:
        c = Config()
        assert c.max_body_size == 10 * 1024 * 1024


class TestConfigFromYaml:
    def test_load_valid_yaml(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("backend: redis\ndefault_ttl: 3600\n")
            f.flush()
            c = Config.from_yaml(f.name)
        Path(f.name).unlink()
        assert c.backend == "redis"
        assert c.default_ttl == 3600

    def test_load_yaml_redis_overrides(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("redis:\n  url: redis://custom:6380\n  key_prefix: \"custom:\"\n")
            f.flush()
            c = Config.from_yaml(f.name)
        Path(f.name).unlink()
        assert c.redis_url == "redis://custom:6380"
        assert c.redis_key_prefix == "custom:"

    def test_yaml_not_found_raises(self) -> None:
        with pytest.raises(ConfigurationError, match="not found"):
            Config.from_yaml("nonexistent.yaml")

    def test_empty_yaml_uses_defaults(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("")
            f.flush()
            c = Config.from_yaml(f.name)
        Path(f.name).unlink()
        assert c.backend == "memory"


class TestConfigFromKwargs:
    def test_single_flat_key(self) -> None:
        c = Config.from_kwargs(default_ttl=7200)
        assert c.default_ttl == 7200
        assert c.backend == "memory"

    def test_redis_keys(self) -> None:
        c = Config.from_kwargs(redis_url="redis://prod:6379", redis_key_prefix="prod:")
        assert c.redis_url == "redis://prod:6379"
        assert c.redis_key_prefix == "prod:"

    def test_partial_redis_overrides_merges_defaults(self) -> None:
        c = Config.from_kwargs(redis_key_prefix="app:")
        assert c.redis_key_prefix == "app:"
        assert c.redis_url == "redis://localhost:6379"

    def test_multiple_keys(self) -> None:
        c = Config.from_kwargs(
            backend="redis",
            default_ttl=1800,
            header_name="X-Idem-Key",
            lock_timeout=10,
        )
        assert c.backend == "redis"
        assert c.default_ttl == 1800
        assert c.header_name == "X-Idem-Key"
        assert c.lock_timeout == 10

    def test_cache_on_status(self) -> None:
        c = Config.from_kwargs(cache_on_status=[200, 201, 204])
        assert c.cache_on_status == [200, 201, 204]


class TestConfigure:
    def test_configure_with_no_args_defaults(self) -> None:
        c = configure()
        assert c.backend == "memory"

    def test_configure_with_kwargs(self) -> None:
        c = configure(backend="redis", default_ttl=60)
        assert c.backend == "redis"
        assert c.default_ttl == 60

    def test_configure_sets_global(self) -> None:
        configure(header_name="X-Key")
        c = get_config()
        assert c.header_name == "X-Key"

    def test_configure_with_yaml_path(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("backend: redis\n")
            f.flush()
            c = configure(config_path=f.name)
        Path(f.name).unlink()
        assert c.backend == "redis"

    def test_get_config_creates_default_if_not_configured(self) -> None:
        import idempot.config as cfg

        cfg._config = None
        c = get_config()
        assert c.backend == "memory"
