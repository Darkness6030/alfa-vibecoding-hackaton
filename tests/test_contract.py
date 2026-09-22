"""Contract and health tests for K1.

These verify the transport contract and the explicit stub behaviour. They do
NOT assert any masking quality: detectors are not implemented yet.
"""

from __future__ import annotations

import fakeredis
from fastapi.testclient import TestClient

import app.main as main
from app.state import StateStore, make_encryption_key

# Use a fakeredis-backed store so contract tests run without a live Redis.
main.store = StateStore(
    redis=fakeredis.FakeRedis(decode_responses=True),
    namespace="test",
    consumer="stand",
    ttl_seconds=900,
    max_record_bytes=1_000_000,
    encryption_key=make_encryption_key(""),
)

client = TestClient(main.app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["engine_stub"] is True


def test_process_returns_200_and_result_string():
    r = client.post("/process", json={"payload": "Иван Иванов", "payload_id": "id-1"})
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"result"}
    assert isinstance(body["result"], str)


def test_process_missing_payload_is_422():
    r = client.post("/process", json={"payload_id": "id-1"})
    assert r.status_code == 422


def test_process_missing_payload_id_is_422():
    r = client.post("/process", json={"payload": "text"})
    assert r.status_code == 422


def test_process_non_string_payload_is_422():
    r = client.post("/process", json={"payload": 123, "payload_id": "id-1"})
    assert r.status_code == 422


def test_process_empty_body_is_422():
    r = client.post("/process", json={})
    assert r.status_code == 422


def test_stub_echoes_and_marks_not_masked():
    # Explicit placeholder behaviour: echo, never claim masking.
    r = client.post("/process", json={"payload": "Иван Иванов", "payload_id": "id-2"})
    assert r.status_code == 200
    assert r.json()["result"] == "Иван Иванов"