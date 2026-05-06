# memory — dict-backed backend, dev only (no real distributed locking)
from __future__ import annotations

import asyncio
import threading
import time
from typing import Optional

from idempot.backends.base import AbstractBackend
from idempot.models import StoredResponse


class MemoryBackend(AbstractBackend):
    def __init__(self) -> None:
        self._store: dict[str, tuple[StoredResponse, float]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._meta_lock = threading.Lock()

    async def get(self, key: str) -> Optional[StoredResponse]:
        entry = self._store.get(key)
        if entry is None:
            return None
        response, expiry = entry
        if time.monotonic() >= expiry:
            del self._store[key]
            return None
        return response

    async def set(self, key: str, response: StoredResponse, ttl: int) -> None:
        expiry = time.monotonic() + ttl
        self._store[key] = (response, expiry)

    async def acquire_lock(self, key: str, timeout: float) -> bool:
        with self._meta_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            lock = self._locks[key]

        try:
            acquired = await asyncio.wait_for(lock.acquire(), timeout=timeout)
            return acquired
        except asyncio.TimeoutError:
            return False

    async def release_lock(self, key: str) -> None:
        with self._meta_lock:
            lock = self._locks.get(key)
        if lock is not None and lock.locked():
            lock.release()
