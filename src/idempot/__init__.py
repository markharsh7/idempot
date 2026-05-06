# idempot __init__ — exports configure(), get_backend(), idempotent decorator
from __future__ import annotations

import functools
from typing import Any, Awaitable, Callable, Iterable

from idempot.backends.base import AbstractBackend
from idempot.backends.memory import MemoryBackend
from idempot.backends.redis import RedisBackend
from idempot.config import configure as configure
from idempot.config import get_config as get_config
from idempot.core import execute
from idempot.exceptions import (
    BackendError as BackendError,
)
from idempot.exceptions import (
    ConfigurationError as ConfigurationError,
)
from idempot.exceptions import (
    IdempotencyError as IdempotencyError,
)
from idempot.exceptions import (
    IdempotencyKeyMissingError as IdempotencyKeyMissingError,
)
from idempot.exceptions import (
    KeyConflictError as KeyConflictError,
)
from idempot.models import StoredResponse

_backend: AbstractBackend | None = None


def get_backend() -> AbstractBackend:
    global _backend
    cfg = get_config()
    if _backend is not None:
        if isinstance(_backend, RedisBackend) and cfg.backend != "redis":
            _backend = MemoryBackend()
        elif isinstance(_backend, MemoryBackend) and cfg.backend == "redis":
            _backend = RedisBackend(
                url=cfg.redis_url, key_prefix=cfg.redis_key_prefix
            )
    else:
        if cfg.backend == "redis":
            _backend = RedisBackend(
                url=cfg.redis_url, key_prefix=cfg.redis_key_prefix
            )
        else:
            _backend = MemoryBackend()
    return _backend


_WrappedFunc = Callable[..., Awaitable[StoredResponse]]
_DecoratedFunc = Callable[..., Awaitable[StoredResponse]]


def idempotent(
    _func: _WrappedFunc | None = None,
    *,
    key: str | None = None,
    ttl: int | None = None,
    required: bool | None = None,
    lock_timeout: int | None = None,
    cache_on_status: Iterable[int] | None = None,
    max_body_size: int | None = None,
) -> Any:
    def decorator(func: _WrappedFunc) -> _DecoratedFunc:
        @functools.wraps(func)
        async def wrapper(**kwargs: Any) -> StoredResponse:
            cfg = get_config()
            effective_key: str | None = key
            if effective_key is None:
                header_lower = cfg.header_name.lower().replace("-", "_")
                effective_key = kwargs.pop(header_lower, None)
                if effective_key is None:
                    effective_key = kwargs.pop("idempotency_key", None)

            async def handler() -> StoredResponse:
                return await func(**kwargs)

            return await execute(
                backend=get_backend(),
                key=effective_key,
                handler=handler,
                required=required if required is not None else False,
                ttl=ttl if ttl is not None else cfg.default_ttl,
                lock_timeout=(
                    lock_timeout if lock_timeout is not None else cfg.lock_timeout
                ),
                cache_on_status=(
                    cache_on_status
                    if cache_on_status is not None
                    else cfg.cache_on_status
                ),
                max_body_size=(
                    max_body_size if max_body_size is not None else cfg.max_body_size
                ),
            )
        return wrapper

    if _func is not None:
        return decorator(_func)
    return decorator
