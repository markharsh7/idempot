# tests for redis backend using fakeredis
from __future__ import annotations

import pytest
from fakeredis import aioredis as fakeredis_aioredis

from idempot.backends.redis import RedisBackend
from idempot.models import StoredResponse


def _make_response(status: int = 200, body: str = "ok") -> StoredResponse:
    return StoredResponse(
        status_code=status,
        headers={"Content-Type": "application/json"},
        body=body.encode(),
    )


@pytest.fixture
async def redis_backend() -> RedisBackend:
    backend = RedisBackend(url="redis://localhost")
    backend._redis = await fakeredis_aioredis.FakeRedis()
    backend._acquire_script = backend._redis.register_script(
        backend._acquire_script.script
    )
    return backend


class TestRedisBackend:
    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing_key(
        self, redis_backend: RedisBackend
    ) -> None:
        result = await redis_backend.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self, redis_backend: RedisBackend) -> None:
        resp = _make_response(body='{"ok":true}')
        await redis_backend.set("key1", resp, ttl=60)
        result = await redis_backend.get("key1")
        assert result is not None
        assert result.status_code == 200
        assert result.body == b'{"ok":true}'
        assert result.headers == {"Content-Type": "application/json"}

    @pytest.mark.asyncio
    async def test_lock_acquire_and_release(self, redis_backend: RedisBackend) -> None:
        acquired = await redis_backend.acquire_lock("lock1", timeout=5)
        assert acquired is True
        await redis_backend.release_lock("lock1")

    @pytest.mark.asyncio
    async def test_lock_prevents_duplicate(self, redis_backend: RedisBackend) -> None:
        acquired = await redis_backend.acquire_lock("lock2", timeout=5)
        assert acquired is True
        double_acquire = await redis_backend.acquire_lock("lock2", timeout=1)
        assert double_acquire is False

    @pytest.mark.asyncio
    async def test_release_then_reacquire(self, redis_backend: RedisBackend) -> None:
        await redis_backend.acquire_lock("lock3", timeout=5)
        await redis_backend.release_lock("lock3")
        acquired = await redis_backend.acquire_lock("lock3", timeout=1)
        assert acquired is True

    @pytest.mark.asyncio
    async def test_different_keys_dont_conflict(
        self, redis_backend: RedisBackend
    ) -> None:
        resp_a = _make_response(body="a")
        resp_b = _make_response(body="b")
        await redis_backend.set("a", resp_a, ttl=60)
        await redis_backend.set("b", resp_b, ttl=60)
        result_a = await redis_backend.get("a")
        result_b = await redis_backend.get("b")
        assert result_a is not None and result_b is not None
        assert result_a.body == b"a"
        assert result_b.body == b"b"

    @pytest.mark.asyncio
    async def test_key_prefix_isolation(self, redis_backend: RedisBackend) -> None:
        resp = _make_response()
        await redis_backend.set("shared", resp, ttl=60)
        result = await redis_backend.get("shared")
        assert result is not None
        result_none = await redis_backend.get("shared-other")
        assert result_none is None
