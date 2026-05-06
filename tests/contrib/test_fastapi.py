# integration tests for FastAPI adapter
from __future__ import annotations

import asyncio
import concurrent.futures
import time

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from idempot import configure
from idempot.contrib.fastapi import idempotent


@pytest.fixture(autouse=True)
def _setup() -> None:
    configure(backend="memory")


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()

    @app.post("/echo")
    @idempotent
    async def echo(request: Request) -> dict:
        body = await request.json()
        return {"echo": body.get("msg", "")}

    @app.get("/text")
    @idempotent
    async def text(request: Request) -> str:
        return "hello world"

    @app.post("/required")
    @idempotent(required=True)
    async def required(request: Request) -> dict:
        return {"ok": True}

    return TestClient(app)


class TestFastAPIAdapter:
    def test_missing_key_passes_through(self, client: TestClient) -> None:
        r1 = client.post("/echo", json={"msg": "hi"})
        assert r1.status_code == 200
        assert r1.json() == {"echo": "hi"}

        r2 = client.post("/echo", json={"msg": "bye"})
        assert r2.status_code == 200
        assert r2.json() == {"echo": "bye"}

    def test_idempotent_replay(self, client: TestClient) -> None:
        h = {"Idempotency-Key": "ik-1"}
        r1 = client.post("/echo", json={"msg": "first"}, headers=h)
        assert r1.status_code == 200
        assert r1.json() == {"echo": "first"}

        r2 = client.post("/echo", json={"msg": "second"}, headers=h)
        assert r2.status_code == 200
        assert r2.json() == {"echo": "first"}

    def test_different_keys_independent(self, client: TestClient) -> None:
        r1 = client.post("/echo", json={"msg": "a"}, headers={"Idempotency-Key": "a"})
        r2 = client.post("/echo", json={"msg": "b"}, headers={"Idempotency-Key": "b"})
        assert r1.json() == {"echo": "a"}
        assert r2.json() == {"echo": "b"}

    def test_text_response(self, client: TestClient) -> None:
        h = {"Idempotency-Key": "text-1"}
        r1 = client.get("/text", headers=h)
        assert r1.status_code == 200
        assert r1.text == "hello world"

        r2 = client.get("/text", headers=h)
        assert r2.status_code == 200
        assert r2.text == "hello world"

    def test_required_key_missing(self, client: TestClient) -> None:
        r = client.post("/required", json={})
        assert r.status_code == 400


class TestFastAPIIdempotentHeaders:
    def test_headers_preserved(self, client: TestClient) -> None:
        r = client.post(
            "/echo",
            json={"msg": "headers"},
            headers={"Idempotency-Key": "hdr-1"},
        )
        assert r.status_code == 200
        assert "content-type" in r.headers


class TestFastAPIConcurrency:
    @pytest.fixture(autouse=True)
    def _setup_override(self) -> None:
        configure(backend="memory", lock_timeout=10)

    def test_racing_requests_same_key(self) -> None:
        counter = 0
        barrier = asyncio.Event()
        app = FastAPI()

        @app.post("/slow")
        @idempotent
        async def slow(request: Request) -> dict:
            nonlocal counter
            counter += 1
            await asyncio.wait_for(barrier.wait(), timeout=5)
            return {"count": counter}

        client = TestClient(app)

        def do_request(msg: str) -> dict:
            return client.post(
                "/slow",
                json={"msg": msg},
                headers={"Idempotency-Key": "concurrent-key"},
            ).json()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(do_request, "first")
            time.sleep(0.2)
            f2 = pool.submit(do_request, "second")
            time.sleep(0.2)
            barrier.set()
            r1 = f1.result(timeout=10)
            r2 = f2.result(timeout=10)

        assert counter == 1
        assert r1 == r2
        assert r1 == {"count": 1}


class TestFastAPIErrorHandling:
    @pytest.fixture(autouse=True)
    def _setup_override(self) -> None:
        configure(backend="memory")

    def test_handler_exception_not_cached(self) -> None:
        app = FastAPI()

        call_count = 0

        @app.post("/fail")
        @idempotent
        async def fail(request: Request) -> dict:
            nonlocal call_count
            call_count += 1
            raise ValueError("simulated error")

        client = TestClient(app, raise_server_exceptions=False)

        h = {"Idempotency-Key": "error-key"}
        r1 = client.post("/fail", headers=h)
        assert r1.status_code == 500
        assert call_count == 1

        r2 = client.post("/fail", headers=h)
        assert r2.status_code == 500
        assert call_count == 2  # not cached because handler raised
