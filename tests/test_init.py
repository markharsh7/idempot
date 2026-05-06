# tests for public API surface (__init__.py)
from __future__ import annotations

import pytest

from idempot import (
    BackendError,
    ConfigurationError,
    IdempotencyError,
    IdempotencyKeyMissingError,
    KeyConflictError,
    configure,
    get_backend,
    get_config,
    idempotent,
)
from idempot.backends.memory import MemoryBackend
from idempot.backends.redis import RedisBackend
from idempot.models import StoredResponse


def _make_response(status: int = 200, body: str = "ok") -> StoredResponse:
    return StoredResponse(
        status_code=status,
        headers={"Content-Type": "text/plain"},
        body=body.encode(),
    )


class TestExports:
    def test_configure_importable(self) -> None:
        assert callable(configure)

    def test_get_config_importable(self) -> None:
        assert callable(get_config)

    def test_get_backend_importable(self) -> None:
        assert callable(get_backend)

    def test_idempotent_importable(self) -> None:
        assert callable(idempotent)

    def test_exceptions_importable(self) -> None:
        assert issubclass(IdempotencyError, Exception)
        assert issubclass(IdempotencyKeyMissingError, IdempotencyError)
        assert issubclass(KeyConflictError, IdempotencyError)
        assert issubclass(BackendError, IdempotencyError)
        assert issubclass(ConfigurationError, IdempotencyError)


class TestGetBackend:
    def test_default_memory_backend(self) -> None:
        backend = get_backend()
        assert isinstance(backend, MemoryBackend)

    def test_redis_backend_from_config(self) -> None:
        configure(backend="redis", redis_url="redis://localhost:6379")
        backend = get_backend()
        assert isinstance(backend, RedisBackend)

    def test_revert_to_memory(self) -> None:
        configure(backend="memory")
        backend = get_backend()
        assert isinstance(backend, MemoryBackend)


class TestIdempotentDecorator:
    def setup_method(self) -> None:
        configure(backend="memory")

    @pytest.mark.asyncio
    async def test_key_from_kwargs(self) -> None:
        call_count = 0

        @idempotent
        async def handler(data: str = "") -> StoredResponse:
            nonlocal call_count
            call_count += 1
            return _make_response(body=data)

        response = await handler(idempotency_key="k1", data="hello")
        assert call_count == 1
        assert response.body == b"hello"

        response2 = await handler(idempotency_key="k1", data="world")
        assert call_count == 1
        assert response2.body == b"hello"

    @pytest.mark.asyncio
    async def test_key_passed_explicitly(self) -> None:
        call_count = 0

        @idempotent(key="explicit-key")
        async def handler(data: str = "") -> StoredResponse:
            nonlocal call_count
            call_count += 1
            return _make_response(body=data)

        await handler(data="first")
        assert call_count == 1

        response2 = await handler(data="second")
        assert call_count == 1
        assert response2.body == b"first"

    @pytest.mark.asyncio
    async def test_key_missing_not_required(self) -> None:
        called = False

        @idempotent
        async def handler() -> StoredResponse:
            nonlocal called
            called = True
            return _make_response()

        response = await handler()
        assert called is True
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_key_missing_required_raises(self) -> None:
        @idempotent(required=True)
        async def handler() -> StoredResponse:
            return _make_response()

        with pytest.raises(IdempotencyKeyMissingError):
            await handler()

    @pytest.mark.asyncio
    async def test_ttl_override(self) -> None:
        from idempot.backends.memory import MemoryBackend

        backend = get_backend()
        assert isinstance(backend, MemoryBackend)

        @idempotent(ttl=0)
        async def handler(data: str = "") -> StoredResponse:
            return _make_response(body=data)

        await handler(idempotency_key="ttl-test", data="x")
        cached = await backend.get("ttl-test")
        assert cached is None

    @pytest.mark.asyncio
    async def test_cache_on_status_override(self) -> None:
        from idempot.backends.memory import MemoryBackend

        backend = get_backend()
        assert isinstance(backend, MemoryBackend)

        @idempotent(cache_on_status=[200, 201])
        async def handler(data: str = "") -> StoredResponse:
            return _make_response(status=201, body=data)

        await handler(idempotency_key="status-test", data="created")
        cached = await backend.get("status-test")
        assert cached is not None
        assert cached.status_code == 201

    @pytest.mark.asyncio
    async def test_bare_decorator_syntax(self) -> None:
        @idempotent
        async def handler(value: str = "bare") -> StoredResponse:
            return _make_response(body=value)

        response = await handler(idempotency_key="bare-key", value="test")
        assert response.body == b"test"

    @pytest.mark.asyncio
    async def test_custom_header_name(self) -> None:
        configure(header_name="X-Idem-Key")
        call_count = 0

        @idempotent
        async def handler(value: str = "") -> StoredResponse:
            nonlocal call_count
            call_count += 1
            return _make_response(body=value)

        await handler(x_idem_key="custom", value="a")
        assert call_count == 1

        await handler(x_idem_key="custom", value="b")
        assert call_count == 1
