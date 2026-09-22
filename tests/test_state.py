"""K2b tests: D05 state machine, atomic publication, TTL, conflict, encryption.

Uses fakeredis so tests run without a live Redis server.
"""

from __future__ import annotations

import threading

import fakeredis
import pytest

from app.core import MaskResult, mask
from app.engine import MaskingEngine
from app.state import ConflictError, StateStore, StorageError, make_encryption_key

KEY = make_encryption_key("")


def _make_store(redis=None, ttl=900):
    return StateStore(
        redis=redis or fakeredis.FakeRedis(decode_responses=True),
        namespace="test",
        consumer="stand",
        ttl_seconds=ttl,
        max_record_bytes=1_000_000,
        encryption_key=KEY,
    )


def _email_mask(text: str) -> MaskResult:
    return mask(text, MaskingEngine().detect(text))


def test_new_id_returns_mask_and_created():
    store = _make_store()
    out = store.process("id-1", "mail a@b.com now", _email_mask)
    assert out.created is True
    assert "a@b.com" not in out.result
    assert "{{EMAIL:" in out.result


def test_repeat_original_returns_same_mask():
    store = _make_store()
    first = store.process("id-1", "mail a@b.com now", _email_mask)
    second = store.process("id-1", "mail a@b.com now", _email_mask)
    assert second.created is False
    assert second.result == first.result


def test_demask_returns_original():
    store = _make_store()
    first = store.process("id-1", "mail a@b.com now", _email_mask)
    back = store.process("id-1", first.result, _email_mask)
    assert back.created is False
    assert back.result == "mail a@b.com now"


def test_demask_repeat_returns_original_again():
    store = _make_store()
    first = store.process("id-1", "mail a@b.com now", _email_mask)
    back1 = store.process("id-1", first.result, _email_mask)
    back2 = store.process("id-1", first.result, _email_mask)
    assert back1.result == "mail a@b.com now"
    assert back2.result == "mail a@b.com now"


def test_conflict_different_text_raises_409():
    store = _make_store()
    store.process("id-1", "mail a@b.com now", _email_mask)
    with pytest.raises(ConflictError):
        store.process("id-1", "completely different text", _email_mask)


def test_no_pii_original_equals_mask_repeat_stable():
    store = _make_store()
    text = "просто текст без персональных данных"
    first = store.process("id-1", text, _email_mask)
    second = store.process("id-1", text, _email_mask)
    assert first.result == text
    assert second.result == text


def test_concurrent_first_single_publication():
    store = _make_store()
    results = []
    errors = []

    def worker():
        try:
            results.append(store.process("id-race", "mail a@b.com now", _email_mask))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    # All outcomes agree on the same mask.
    masks = {r.result for r in results}
    assert len(masks) == 1
    assert "a@b.com" not in masks.pop()
    # Exactly one writer created the pair.
    assert sum(1 for r in results if r.created) == 1


def test_redis_unavailable_raises_storage_error():
    class BrokenRedis:
        def set(self, *a, **k):
            raise ConnectionError("down")

        def get(self, *a, **k):
            raise ConnectionError("down")

    store = _make_store(redis=BrokenRedis())
    with pytest.raises(StorageError):
        store.process("id-1", "mail a@b.com now", _email_mask)


def test_oversized_payload_raises_storage_error():
    store = StateStore(
        redis=fakeredis.FakeRedis(decode_responses=True),
        namespace="test",
        consumer="stand",
        ttl_seconds=900,
        max_record_bytes=10,
        encryption_key=KEY,
    )
    with pytest.raises(StorageError):
        store.process("id-1", "x" * 100, _email_mask)


def test_ttl_expiry_allows_new_publication():
    store = _make_store(ttl=1)
    first = store.process("id-1", "mail a@b.com now", _email_mask)
    # Simulate TTL expiry by clearing the key.
    store._redis.flushall()
    second = store.process("id-1", "mail a@b.com now", _email_mask)
    # After expiry the id is treated as new: a fresh pair is published.
    assert second.created is True
    assert "a@b.com" not in second.result


def test_mapping_values_encrypted_in_redis():
    store = _make_store()
    store.process("id-1", "mail a@b.com now", _email_mask)
    raw = store._redis.get(store._key("id-1"))
    # The original PII must not appear in plaintext in the stored record.
    assert "a@b.com" not in raw
    assert "mail a@b.com now" not in raw


def test_shared_key_across_stores_restores():
    # Two stores sharing the same redis and key can demask each other's records.
    shared = fakeredis.FakeRedis(decode_responses=True)
    store1 = _make_store(redis=shared)
    store2 = _make_store(redis=shared)
    first = store1.process("id-1", "mail a@b.com now", _email_mask)
    back = store2.process("id-1", first.result, _email_mask)
    assert back.result == "mail a@b.com now"