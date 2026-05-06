# tests for core idempotency engine
from __future__ import annotations

import asyncio

import pytest

from idempot.backends.memory import MemoryBackend
from idempot.core import execute
from idempot.exceptions import IdempotencyKeyMissingError, KeyConflictError
from idempot.models import StoredResponse


def _make_response(status: int = 200, body: str = "ok") -> StoredResponse:
    return StoredResponse(
        status_code=status,
        headers={"Content-Type": "text/plain"},
        body=body.encode(),
    )


class TestCoreKeyHandling:
    @pytest.fixture
    def backend(self) -> MemoryBackend:
        return MemoryBackend()

    @pytest.mark.asyncio
    async def test_key_missing_required_raises(self, backend: MemoryBackend) -> None:
        async def handler() -> StoredResponse:
            return _make_response()

        with pytest.raises(IdempotencyKeyMissingError, match="required"):
            await execute(backend, None, handler, required=True)

    @pytest.mark.asyncio
    async def test_key_missing_not_required_passes_through(
        self, backend: MemoryBackend
    ) -> None:
        called = False

        async def handler() -> StoredResponse:
            nonlocal called
            called = True
            return _make_response()

        response = await execute(backend, None, handler, required=False)
        assert called is True
        assert response.status_code == 200


class TestCoreHappyPath:
    @pytest.fixture
    def backend(self) -> MemoryBackend:
        return MemoryBackend()

    @pytest.mark.asyncio
    async def test_execute_and_cache(self, backend: MemoryBackend) -> None:
        call_count = 0

        async def handler() -> StoredResponse:
            nonlocal call_count
            call_count += 1
            return _make_response()

        response = await execute(backend, "key-abc", handler, ttl=60)
        assert response.status_code == 200
        assert call_count == 1

        cached = await backend.get("key-abc")
        assert cached is not None
        assert cached.body == b"ok"

    @pytest.mark.asyncio
    async def test_replay_cached_response(self, backend: MemoryBackend) -> None:
        call_count = 0

        async def handler() -> StoredResponse:
            nonlocal call_count
            call_count += 1
            return _make_response()

        first = await execute(backend, "key-xyz", handler, ttl=60)
        assert call_count == 1
        assert first.status_code == 200

        second = await execute(backend, "key-xyz", handler, ttl=60)
        assert call_count == 1
        assert second.status_code == 200


class TestCoreConcurrency:
    @pytest.fixture
    def backend(self) -> MemoryBackend:
        return MemoryBackend()

    @pytest.mark.asyncio
    async def test_concurrent_second_gets_cached(self, backend: MemoryBackend) -> None:
        call_count = 0
        event = asyncio.Event()

        async def handler() -> StoredResponse:
            nonlocal call_count
            call_count += 1
            await event.wait()
            return _make_response()

        async def first_request() -> StoredResponse:
            return await execute(backend, "key-conc", handler, ttl=60, lock_timeout=10)

        async def second_request() -> StoredResponse:
            return await execute(backend, "key-conc", handler, ttl=60, lock_timeout=10)

        task1 = asyncio.create_task(first_request())
        await asyncio.sleep(0.05)
        task2 = asyncio.create_task(second_request())
        await asyncio.sleep(0.05)
        event.set()

        r1, r2 = await asyncio.gather(task1, task2)
        assert call_count == 1
        assert r1.status_code == 200
        assert r2.status_code == 200

    @pytest.mark.asyncio
    async def test_concurrent_timeout_raises_conflict(
        self, backend: MemoryBackend
    ) -> None:
        event = asyncio.Event()

        async def handler() -> StoredResponse:
            await event.wait()
            return _make_response()

        task1 = asyncio.create_task(
            execute(backend, "key-conflict", handler, ttl=60, lock_timeout=1)
        )
        await asyncio.sleep(0.05)

        with pytest.raises(KeyConflictError):
            await execute(backend, "key-conflict", handler, ttl=60, lock_timeout=1)

        event.set()
        await task1


class TestCoreExclusions:
    @pytest.fixture
    def backend(self) -> MemoryBackend:
        return MemoryBackend()

    @pytest.mark.asyncio
    async def test_handler_error_not_cached(self, backend: MemoryBackend) -> None:
        async def handler() -> StoredResponse:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await execute(backend, "key-err", handler, ttl=60)

        cached = await backend.get("key-err")
        assert cached is None

    @pytest.mark.asyncio
    async def test_status_not_in_cache_on_status(self, backend: MemoryBackend) -> None:
        async def handler() -> StoredResponse:
            return _make_response(status=400, body="bad request")

        response = await execute(
            backend, "key-400", handler, ttl=60, cache_on_status=[200, 201]
        )
        assert response.status_code == 400
        cached = await backend.get("key-400")
        assert cached is None

    @pytest.mark.asyncio
    async def test_body_exceeds_max_size_not_cached(self, backend: MemoryBackend) -> None:
        async def handler() -> StoredResponse:
            return _make_response(body="x" * 2000)

        response = await execute(
            backend, "key-big", handler, ttl=60, max_body_size=100
        )
        assert response.status_code == 200
        cached = await backend.get("key-big")
        assert cached is None

    @pytest.mark.asyncio
    async def test_lock_released_after_handler_error(
        self, backend: MemoryBackend
    ) -> None:
        async def handler() -> StoredResponse:
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError, match="fail"):
            await execute(backend, "key-lock-err", handler, ttl=60, lock_timeout=5)

        acquired = await backend.acquire_lock("key-lock-err", timeout=0.1)
        assert acquired is True


class TestCoreBackendErrors:
    @pytest.fixture
    def backend(self) -> MemoryBackend:
        return MemoryBackend()

    @pytest.mark.asyncio
    async def test_backend_get_failure_propagates(self, backend: MemoryBackend) -> None:
        failing_backend = _FailingBackend("get")

        async def handler() -> StoredResponse:
            return _make_response()

        with pytest.raises(RuntimeError, match="backend get error"):
            await execute(failing_backend, "key1", handler, ttl=60)

    @pytest.mark.asyncio
    async def test_backend_set_failure_does_not_crash(
        self, backend: MemoryBackend
    ) -> None:
        failing_backend = _FailingBackend("set")

        async def handler() -> StoredResponse:
            return _make_response()

        with pytest.raises(RuntimeError, match="backend set error"):
            await execute(failing_backend, "key2", handler, ttl=60)

    @pytest.mark.asyncio
    async def test_backend_lock_failure_propagates(
        self, backend: MemoryBackend
    ) -> None:
        failing_backend = _FailingBackend("acquire_lock")

        async def handler() -> StoredResponse:
            return _make_response()

        with pytest.raises(RuntimeError, match="backend lock error"):
            await execute(failing_backend, "key3", handler, ttl=60)


class _FailingBackend:
    def __init__(self, fail_on: str) -> None:
        self._fail_on = fail_on

    async def get(self, key: str) -> None:
        if self._fail_on == "get":
            raise RuntimeError("backend get error")
        return None

    async def set(self, key: str, response: StoredResponse, ttl: int) -> None:
        if self._fail_on == "set":
            raise RuntimeError("backend set error")
        return None

    async def acquire_lock(self, key: str, timeout: float) -> bool:
        if self._fail_on == "acquire_lock":
            raise RuntimeError("backend lock error")
        return True

    async def release_lock(self, key: str) -> None:
        return None
