# tests for memory backend
from __future__ import annotations

import pytest

from idempot.backends.memory import MemoryBackend
from idempot.models import StoredResponse


def _make_response(status: int = 200, body: str = "ok") -> StoredResponse:
    return StoredResponse(
        status_code=status,
        headers={"Content-Type": "text/plain"},
        body=body.encode(),
    )


class TestMemoryBackend:
    @pytest.fixture
    def backend(self) -> MemoryBackend:
        return MemoryBackend()

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing_key(self, backend: MemoryBackend) -> None:
        result = await backend.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self, backend: MemoryBackend) -> None:
        resp = _make_response()
        await backend.set("key1", resp, ttl=60)
        result = await backend.get("key1")
        assert result is not None
        assert result.status_code == 200
        assert result.body == b"ok"
        assert result.headers == {"Content-Type": "text/plain"}

    @pytest.mark.asyncio
    async def test_ttl_expiry(self, backend: MemoryBackend) -> None:
        resp = _make_response()
        await backend.set("key2", resp, ttl=0)
        result = await backend.get("key2")
        assert result is None

    @pytest.mark.asyncio
    async def test_lock_acquire_and_release(self, backend: MemoryBackend) -> None:
        acquired = await backend.acquire_lock("lock1", timeout=1)
        assert acquired is True
        await backend.release_lock("lock1")

    @pytest.mark.asyncio
    async def test_lock_blocks_concurrent(self, backend: MemoryBackend) -> None:
        await backend.acquire_lock("lock2", timeout=2)

        async def try_acquire() -> bool:
            return await backend.acquire_lock("lock2", timeout=0.1)

        result = await try_acquire()
        assert result is False

    @pytest.mark.asyncio
    async def test_release_then_reacquire(self, backend: MemoryBackend) -> None:
        await backend.acquire_lock("lock3", timeout=2)
        await backend.release_lock("lock3")
        acquired = await backend.acquire_lock("lock3", timeout=0.1)
        assert acquired is True
