# idempot

Idempotency for APIs via decorators. Framework-agnostic core with adapters for FastAPI and Flask.

## Install

```bash
pip install idempot                  # core + backends (pyyaml, redis)
pip install "idempot[fastapi]"       # core + fastapi
pip install "idempot[flask]"         # core + flask
pip install "idempot[dev]"           # everything + test/lint deps
```

## Zero-config Quickstart

No config needed. Import, decorate, done.

### FastAPI

```python
# app.py
from fastapi import FastAPI, Request
from idempot.contrib.fastapi import idempotent

app = FastAPI()

@app.post("/charge")
@idempotent
async def charge(request: Request):
    body = await request.json()
    return {"charged": body["amount"]}
```

```bash
uvicorn app:app --reload
```

### Flask

```python
# app.py
import flask
from idempot.contrib.flask import idempotent

app = flask.Flask(__name__)

@app.post("/charge")
@idempotent
def charge():
    data = flask.request.get_json()
    return flask.jsonify({"charged": data["amount"]})
```

```bash
flask --app app run
```

Defaults: memory backend, 24h TTL, `Idempotency-Key` header, 5s lock timeout.

## Client Usage

Send `Idempotency-Key` header with every request:

```bash
curl -X POST http://localhost:8000/charge \
  -H "Idempotency-Key: abc-123" \
  -H "Content-Type: application/json" \
  -d '{"amount": 99}'
# → {"charged": 99}

# Same key → replayed response (handler not called)
curl -X POST http://localhost:8000/charge \
  -H "Idempotency-Key: abc-123" \
  -H "Content-Type: application/json" \
  -d '{"amount": 50}'        # different body, ignored
# → {"charged": 99}           # same reply
```

## Configuration

### Option A — `configure()` at startup

In your app entry point, before registering routes:

```python
from idempot import configure

# Redis in production:
configure(
    backend="redis",
    redis_url="redis://localhost:6379",
    redis_key_prefix="myapp:",
    default_ttl=86400,
    header_name="Idempotency-Key",
    lock_timeout=5,
    cache_on_status=[200, 201],
)

# Or override just one thing:
configure(backend="memory", default_ttl=3600)
```

### Option B — YAML file

Create `idempot-config.yaml` in your project root:

```yaml
backend: redis
redis:
  url: redis://localhost:6379
  key_prefix: "myapp:"
default_ttl: 86400
header_name: Idempotency-Key
lock_timeout: 5
cache_on_status: [200, 201]
```

```python
from idempot import configure
configure(config_path="idempot-config.yaml")
```

A working example file: [`idempot-config.example.yaml`](idempot-config.example.yaml)

The config file is **not** auto-generated. If no config file is found and `configure()` is never called, memory backend + defaults are used.

### Config reference

| Key | Default | Description |
|---|---|---|
| `backend` | `memory` | `memory` or `redis` |
| `redis.url` | `redis://localhost:6379` | Redis connection URL |
| `redis.key_prefix` | `idempot:` | Prefix for Redis keys |
| `default_ttl` | `86400` (24h) | Seconds before cached response expires |
| `header_name` | `Idempotency-Key` | HTTP header to read the key from |
| `lock_timeout` | `5` | Max seconds to wait for concurrent same-key request |
| `cache_on_status` | `[200]` | Which HTTP status codes get cached |
| `max_body_size` | `10485760` (10 MB) | Largest response body to cache |

## Per-endpoint Overrides

```python
@app.post("/payments")
@idempotent(
    ttl=3600,                      # cache 1 hour (instead of default 24h)
    required=True,                 # reject requests without key → 400
    cache_on_status=[200, 201],    # cache on 200 or 201
    lock_timeout=10,               # wait up to 10s for concurrent
)
async def process_payment(request: Request):
    ...
```

Override params: `ttl`, `required`, `lock_timeout`, `cache_on_status`, `max_body_size`.

## Import Cheatsheet

| Context | Import |
|---|---|
| Config & setup | `from idempot import configure, get_config` |
| FastAPI decorator | `from idempot.contrib.fastapi import idempotent` |
| Flask decorator | `from idempot.contrib.flask import idempotent` |
| Base decorator (no framework) | `from idempot import idempotent` |
| Exceptions | `from idempot import IdempotencyKeyMissingError, KeyConflictError` |
| Backends (custom) | `from idempot.backends.memory import MemoryBackend` |

## How It Works

1. Decorator reads `Idempotency-Key` from request headers
2. Key missing → 400 if `required=True`, otherwise handler runs normally (not cached)
3. Key in cache → replays stored response verbatim (same status, headers, body)
4. Key new → acquires distributed lock (Redis `SETNX`) → runs handler → caches response → releases lock
5. Concurrent same-key → second request polls for cached response, returns it. If first request exceeds `lock_timeout` → 409 Conflict

## Backends

- **Memory** (default, dev): dict-backed, no persistence
- **Redis** (prod): `SETNX` locks, `SETEX` caching with TTL, key prefix isolation

## License

MIT
