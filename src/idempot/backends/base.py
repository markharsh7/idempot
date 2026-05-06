# base — abstract backend interface for idempotency storage
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from idempot.models import StoredResponse


class AbstractBackend(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[StoredResponse]:
        ...

    @abstractmethod
    async def set(self, key: str, response: StoredResponse, ttl: int) -> None:
        ...

    @abstractmethod
    async def acquire_lock(self, key: str, timeout: float) -> bool:
        ...

    @abstractmethod
    async def release_lock(self, key: str) -> None:
        ...
