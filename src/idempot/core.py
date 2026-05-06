# core — idempotency engine: extract key → check store → lock → execute → cache → reply
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Iterable

from idempot.backends.base import AbstractBackend
from idempot.exceptions import IdempotencyKeyMissingError, KeyConflictError
from idempot.models import StoredResponse

LOCK_POLL_INTERVAL = 0.1


def _should_cache(
    response: StoredResponse,
    cache_on_status: Iterable[int],
    max_body_size: int,
) -> bool:
    if response.status_code not in cache_on_status:
        return False
    if len(response.body) > max_body_size:
        return False
    return True


async def execute(
    backend: AbstractBackend,
    key: str | None,
    handler: Callable[[], Awaitable[StoredResponse]],
    required: bool = False,
    ttl: int = 86400,
    lock_timeout: int = 5,
    cache_on_status: Iterable[int] = (200,),
    max_body_size: int = 10 * 1024 * 1024,
) -> StoredResponse:
    if not key:
        if required:
            raise IdempotencyKeyMissingError("Idempotency-Key header is required")
        return await handler()

    cached = await backend.get(key)
    if cached is not None:
        return cached

    lock_acquired = await backend.acquire_lock(key, timeout=lock_timeout)
    if not lock_acquired:
        deadline = time.monotonic() + lock_timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(LOCK_POLL_INTERVAL)
            cached = await backend.get(key)
            if cached is not None:
                return cached
        raise KeyConflictError(
            f"Concurrent request with key '{key}' still in progress"
        )

    try:
        cached = await backend.get(key)
        if cached is not None:
            return cached
        response = await handler()
        if _should_cache(response, cache_on_status, max_body_size):
            await backend.set(key, response, ttl)
        return response
    finally:
        await backend.release_lock(key)
