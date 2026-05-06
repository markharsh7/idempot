# integration tests for Flask adapter
from __future__ import annotations

import json

import flask
import pytest

from idempot import configure
from idempot.contrib.flask import idempotent


@pytest.fixture(autouse=True)
def _setup() -> None:
    configure(backend="memory")


@pytest.fixture
def client() -> flask.testing.FlaskClient:
    app = flask.Flask(__name__)

    @app.post("/echo")
    @idempotent
    def echo() -> flask.Response:
        data = flask.request.get_json()
        return flask.jsonify({"echo": data.get("msg", "")})

    @app.get("/text")
    @idempotent
    def text() -> flask.Response:
        return flask.Response("hello world", mimetype="text/plain")

    @app.post("/required")
    @idempotent(required=True)
    def required() -> flask.Response:
        return flask.jsonify({"ok": True})

    return app.test_client()


class TestFlaskAdapter:
    def test_missing_key_passes_through(self, client: flask.testing.FlaskClient) -> None:
        r1 = client.post("/echo", json={"msg": "hi"})
        assert r1.status_code == 200
        assert json.loads(r1.data) == {"echo": "hi"}

        r2 = client.post("/echo", json={"msg": "bye"})
        assert r2.status_code == 200
        assert json.loads(r2.data) == {"echo": "bye"}

    def test_idempotent_replay(self, client: flask.testing.FlaskClient) -> None:
        h = {"Idempotency-Key": "ik-1"}
        r1 = client.post("/echo", json={"msg": "first"}, headers=h)
        assert r1.status_code == 200
        assert json.loads(r1.data) == {"echo": "first"}

        r2 = client.post("/echo", json={"msg": "second"}, headers=h)
        assert r2.status_code == 200
        assert json.loads(r2.data) == {"echo": "first"}

    def test_different_keys_independent(self, client: flask.testing.FlaskClient) -> None:
        r1 = client.post("/echo", json={"msg": "a"}, headers={"Idempotency-Key": "a"})
        r2 = client.post("/echo", json={"msg": "b"}, headers={"Idempotency-Key": "b"})
        assert json.loads(r1.data) == {"echo": "a"}
        assert json.loads(r2.data) == {"echo": "b"}

    def test_text_response(self, client: flask.testing.FlaskClient) -> None:
        h = {"Idempotency-Key": "text-1"}
        r1 = client.get("/text", headers=h)
        assert r1.status_code == 200
        assert r1.data == b"hello world"

        r2 = client.get("/text", headers=h)
        assert r2.status_code == 200
        assert r2.data == b"hello world"

    def test_required_key_missing(self, client: flask.testing.FlaskClient) -> None:
        r = client.post("/required", json={})
        assert r.status_code == 400
