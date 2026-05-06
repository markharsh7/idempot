# redis — Redis-backed storage with SETNX locks and SETEX caching
from __future__ import annotations

import json
from typing import Optional

import redis.asyncio as aioredis

from idempot.backends.base import AbstractBackend
from idempot.models import StoredResponse

_ACQUIRE_LOCK_SCRIPT = """
if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'EX', ARGV[2]) then
    return 1
end
return 0
"""


class RedisBackend(AbstractBackend):
    def __init__(self, url: str, key_prefix: str = "idempot:") -> None:
        self._redis = aioredis.from_url(url)
        self._key_prefix = key_prefix
        self._acquire_script = self._redis.register_script(_ACQUIRE_LOCK_SCRIPT)

    def _response_key(self, key: str) -> str:
        return f"{self._key_prefix}resp:{key}"

    def _lock_key(self, key: str) -> str:
        return f"{self._key_prefix}lock:{key}"

    async def get(self, key: str) -> Optional[StoredResponse]:
        raw = await self._redis.get(self._response_key(key))
        if raw is None:
            return None
        return self._deserialize(raw)

    async def set(self, key: str, response: StoredResponse, ttl: int) -> None:
        await self._redis.setex(
            self._response_key(key),
            ttl,
            self._serialize(response),
        )

    async def acquire_lock(self, key: str, timeout: float) -> bool:
        lock_key = self._lock_key(key)
        ttl = max(1, int(timeout))
        result = await self._acquire_script(
            keys=[lock_key],
            args=["1", str(ttl)],
        )
        return bool(result)

    async def release_lock(self, key: str) -> None:
        await self._redis.delete(self._lock_key(key))

    def _serialize(self, response: StoredResponse) -> bytes:
        return json.dumps({
            "status_code": response.status_code,
            "headers": response.headers,
            "body": response.body.hex(),
        }).encode()

    def _deserialize(self, raw: bytes) -> StoredResponse:
        data = json.loads(raw)
        return StoredResponse(
            status_code=data["status_code"],
            headers=data["headers"],
            body=bytes.fromhex(data["body"]),
        )
