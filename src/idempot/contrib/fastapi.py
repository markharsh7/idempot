# contrib/fastapi — @idempotent decorator for FastAPI route handlers
from __future__ import annotations

import functools
import json
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from idempot import get_backend, get_config
from idempot.core import execute
from idempot.exceptions import IdempotencyKeyMissingError, KeyConflictError
from idempot.models import StoredResponse


def _to_stored(result: Any) -> StoredResponse:
    if isinstance(result, Response):
        body = getattr(result, "body", b"")
        if not isinstance(body, bytes):
            body = b""
        return StoredResponse(
            status_code=result.status_code,
            headers=dict(result.headers),
            body=body,
        )
    if isinstance(result, (dict, list)):
        body = json.dumps(result).encode()
        return StoredResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=body,
        )
    if isinstance(result, str):
        body = result.encode()
        return StoredResponse(
            status_code=200,
            headers={"content-type": "text/plain"},
            body=body,
        )
    raise TypeError(f"Unsupported return type for idempotency: {type(result)}")


def _from_stored(stored: StoredResponse) -> Response:
    return Response(
        content=stored.body,
        status_code=stored.status_code,
        headers=stored.headers,
    )


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
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Response:
            cfg = get_config()
            request = kwargs.get("request") or next(
                (v for v in kwargs.values() if isinstance(v, Request)), None
            )
            key: str | None = None
            if request is not None:
                key = request.headers.get(cfg.header_name)

            async def handler() -> StoredResponse:
                result = await func(*args, **kwargs)
                return _to_stored(result)

            try:
                stored = await execute(
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
                return Response(status_code=400, content=b"Idempotency-Key header is required")
            except KeyConflictError:
                return Response(status_code=409, content=b"Request is still in progress")

            return _from_stored(stored)
        return wrapper

    if _func is not None:
        return decorator(_func)
    return decorator
