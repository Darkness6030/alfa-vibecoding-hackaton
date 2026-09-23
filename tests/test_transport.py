"""ASGI admission and buffering invariants independent of framework internals."""

import asyncio
import threading
import pytest
from app.boundary import BoundaryMiddleware


def exercise(messages, limit=8, fail=False):
    sent, bodies = [], []
    gate = threading.BoundedSemaphore(1)

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        bodies.append((await receive())["body"])
        if fail:
            raise ValueError("SYNTHETIC_SECRET_MUST_NOT_ESCAPE")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    app = BoundaryMiddleware(downstream, lambda: gate, lambda: limit)
    asyncio.run(app({"type": "http", "path": "/process"}, receive, send))
    assert gate.acquire(blocking=False)
    return sent, bodies


def test_chunked_body_is_replayed_exactly():
    sent, bodies = exercise(
        [
            {"type": "http.request", "body": b"ab", "more_body": True},
            {"type": "http.request", "body": b"cd", "more_body": False},
        ]
    )
    assert bodies == [b"abcd"]
    assert sent[0]["status"] == 200
    assert (b"cache-control", b"no-store") in sent[0]["headers"]


def test_oversized_chunked_body_never_reaches_processing():
    sent, bodies = exercise(
        [
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"6789", "more_body": False},
        ]
    )
    assert not bodies
    assert sent[0]["status"] == 413


def test_disconnected_input_does_not_create_state():
    sent, bodies = exercise([{"type": "http.disconnect"}])
    assert not sent and not bodies


def test_unexpected_exception_returns_safe_response(caplog):
    sent, bodies = exercise([{"type": "http.request", "body": b"x"}], fail=True)
    assert sent[0]["status"] == 500
    assert b"SYNTHETIC_SECRET" not in sent[1]["body"]
    assert "SYNTHETIC_SECRET" not in caplog.text


def test_cached_engine_follows_policy_changes(monkeypatch):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    import app.main as main

    client = TestClient(main.app)
    first = main._engine("stand")
    assert main._engine("stand") is first
    original = main.policy.systems["stand"]
    main.policy.systems["stand"] = replace(original, mask_types=frozenset({"EMAIL"}))
    assert main._engine("stand") is not first
    assert (
        main._engine("stand").mask("Клиент Иван Петров").masked_text
        == "Клиент Иван Петров"
    )
    main.policy.systems["stand"] = original
    body = {"payload": "Email: a@example.com", "payload_id": "lazy-engine"}
    mask = client.post("/process", json=body).json()["result"]

    def unexpected_engine(system):
        pytest.fail("Retry/restore must not build or invoke detector")

    monkeypatch.setattr(main, "_engine", unexpected_engine)
    assert client.post("/process", json=body).json()["result"] == mask
    body["payload"] = mask
    assert client.post("/process", json=body).json()["result"] == "Email: a@example.com"
