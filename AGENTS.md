# AGENTS.md — idempot

## What this is
Python library providing idempotency for APIs via decorators. Core is framework-agnostic; adapters for FastAPI and Flask.

## Stack
- Python 3.10+
- pip + setuptools (pyproject.toml)
- ruff (lint), mypy (typecheck), pytest + pytest-asyncio (test)
- fakeredis for Redis backend tests (no real Redis in CI)

## Dev commands
```
pip install -e ".[dev]"
ruff check .
mypy src/
pytest                           # all tests
pytest tests/test_core.py        # single file
pytest -k "test_lock"            # single test
```

## Architecture

```
idempot/
├── __init__.py       # exports: configure(), idempotent
├── config.py         # YAML loading, global Config singleton
├── core.py           # engine: extract key → check store → lock → execute → cache → reply
├── exceptions.py     # IdempotencyKeyMissingError, KeyConflictError
├── models.py         # StoredResponse (status_code, headers, body, created_at)
├── backends/
│   ├── base.py       # AbstractBackend: get, set, acquire_lock, release_lock
│   ├── memory.py     # dict-backed, dev only (no real locking)
│   └── redis.py      # Redis with SETNX locks, SETEX cache, Lua scripts
├── contrib/
│   ├── fastapi.py    # @idempotent decorator for FastAPI routes
│   └── flask.py      # @idempotent decorator for Flask views
└── py.typed
```

## Key design decisions

### Config layer
- Load `idempot-config.yaml` via `configure(path)` or pass kwargs programmatically
- Settings: backend, redis URL, key prefix, default_ttl (24h), header_name, lock_timeout (5s)
- Config file missing → fall back to memory backend + defaults (dev-friendly)

### Idempotency flow
1. Decorator reads `Idempotency-Key` from request headers
2. Key missing → if `required=True` reject 400, if `required=False` pass through
3. Core engine checks backend: key exists → replay cached response verbatim
4. Key new → acquire distributed lock (SETNX) → execute handler → store StoredResponse → release lock
5. Concurrent same-key: second request blocks on lock, polls for cached response, returns it. If lock_timeout exceeded → 409 Conflict

### Response caching
- Only cache on success (2xx by default, configurable via `cache_on_status`)
- Skip for streaming responses (detect StreamingResponse)
- Max body size configurable, reject oversized responses

### Per-endpoint overrides
```python
@idempotent(ttl=3600, required=True, cache_on_status=[200, 201])
```

## Testing
- Unit tests: core.py, config.py, backends (memory + redis via fakeredis)
- Integration tests: contrib/fastapi.py and contrib/flask.py using TestClient
- Concurrency tests: use asyncio.gather to simulate racing requests
