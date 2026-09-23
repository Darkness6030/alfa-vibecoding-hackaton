"""K5b tests: metrics, safe logging, 429 with Retry-After.

Uses fakeredis-backed store and the evaluation-open profile.
"""

from __future__ import annotations

import fakeredis
from fastapi.testclient import TestClient

import app.main as main
from app.state import StateStore, make_encryption_key

# Patch store with fakeredis.
main.store = StateStore(
    redis=fakeredis.FakeRedis(decode_responses=True),
    namespace="test",
    consumer="stand",
    ttl_seconds=900,
    max_record_bytes=1_000_000,
    encryption_key=make_encryption_key(""),
)

client = TestClient(main.app)


def test_metrics_endpoint_returns_prometheus_format():
    r = client.get("/metrics", headers={"X-API-Key": "test-crm-only"})
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    body = r.text
    assert "alfagen_http_requests_total" in body


def test_process_records_metrics():
    client.post("/process", json={"payload": "почта a@b.com", "payload_id": "m-1"})
    body = client.get("/metrics", headers={"X-API-Key": "test-crm-only"}).text
    assert "alfagen_pairs_created_total" in body
    assert "alfagen_process_latency_seconds" in body


def test_metrics_do_not_leak_payload():
    client.post("/process", json={"payload": "почта a@b.com", "payload_id": "m-2"})
    body = client.get("/metrics", headers={"X-API-Key": "test-crm-only"}).text
    # No payload text, no payload_id, no email value in metrics.
    assert "a@b.com" not in body
    assert "m-2" not in body


def test_429_returns_retry_after():
    # Force the semaphore to be exhausted.
    main._semaphore = __import__("threading").BoundedSemaphore(0)
    try:
        r = client.post(
            "/process", json={"payload": "почта a@b.com", "payload_id": "m-3"}
        )
        assert r.status_code == 429
        assert r.headers.get("Retry-After") == "1"
    finally:
        main._semaphore = __import__("threading").BoundedSemaphore(
            main._concurrency_limit
        )


def test_429_does_not_leak_payload():
    main._semaphore = __import__("threading").BoundedSemaphore(0)
    try:
        r = client.post(
            "/process", json={"payload": "почта a@b.com", "payload_id": "m-4"}
        )
        assert "a@b.com" not in r.text
        assert "m-4" not in r.text
    finally:
        main._semaphore = __import__("threading").BoundedSemaphore(
            main._concurrency_limit
        )


def test_error_metrics_recorded():
    # Conflict -> 409 -> error metric.
    client.post("/process", json={"payload": "почта a@b.com", "payload_id": "m-5"})
    client.post("/process", json={"payload": "другой текст", "payload_id": "m-5"})
    body = client.get("/metrics", headers={"X-API-Key": "test-crm-only"}).text
    assert "alfagen_errors_total" in body


def test_logs_do_not_contain_payload():
    import io
    import logging

    from app.main import logger

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    try:
        client.post("/process", json={"payload": "почта a@b.com", "payload_id": "m-6"})
        log_text = stream.getvalue()
        assert "a@b.com" not in log_text
        assert "m-6" not in log_text
        assert "почта" not in log_text
    finally:
        logger.removeHandler(handler)
