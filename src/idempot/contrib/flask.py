# contrib/flask — @idempotent decorator for Flask view functions
from __future__ import annotations

import asyncio
import functools
import json
from typing import Any

import flask

from idempot import get_backend, get_config
from idempot.core import execute
from idempot.exceptions import IdempotencyKeyMissingError, KeyConflictError
from idempot.models import StoredResponse


def _to_stored(result: Any) -> StoredResponse:
    status_code = 200
    headers: dict[str, str] = {}
    body: bytes = b""

    if isinstance(result, flask.Response):
        status_code = result.status_code
        headers = dict(result.headers)
        body = result.get_data() or b""
    elif isinstance(result, tuple):
        body_raw = result[0]
        if len(result) > 1:
            status_code = result[1]
        if len(result) > 2:
            headers = dict(result[2])
        body = body_raw.encode() if isinstance(body_raw, str) else body_raw
    elif isinstance(result, dict):
        body = json.dumps(result).encode()
        headers = {"content-type": "application/json"}
    elif isinstance(result, str):
        body = result.encode()
        headers = {"content-type": "text/html"}
    elif result is not None:
        body = str(result).encode()
        headers = {"content-type": "text/plain"}

    return StoredResponse(
        status_code=status_code,
        headers=headers,
        body=body,
    )


def _from_stored(stored: StoredResponse) -> flask.Response:
    return flask.Response(
        response=stored.body,
        status=stored.status_code,
        headers=stored.headers,
    )


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)


def idempotent(
    _func: Any = None,
    *,
    ttl: int | None = None,
    required: bool | None = None,
    lock_timeout: int | None = None,
    cache_on_status: list[int] | None = None,
    max_body_size: int | None = None,
) -> Any:
    def decorator(func: Any) -> Any:
        cfg = get_config()

        async def _execute(
            key: str | None, handler_func: Any, *args: Any, **kwargs: Any
        ) -> StoredResponse:
            async def handler() -> StoredResponse:
                result = handler_func(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                return _to_stored(result)

            try:
                return await execute(
                    backend=get_backend(),
                    key=key,
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
            except IdempotencyKeyMissingError:
                return StoredResponse(
                    status_code=400,
                    headers={},
                    body=b"Idempotency-Key header is required",
                )
            except KeyConflictError:
                return StoredResponse(
                    status_code=409,
                    headers={},
                    body=b"Request is still in progress",
                )

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> flask.Response:
            key = flask.request.headers.get(cfg.header_name)
            stored = _run_async(_execute(key, func, *args, **kwargs))
            return _from_stored(stored)

        return wrapper

    if _func is not None:
        return decorator(_func)
    return decorator
