"""K8 tests: large input up to 100k tokens, no truncation, exact round-trip.

Uses the declared tokenizer (app/tokenizer.py). Verifies that masking and
restoration handle a large text without truncation or edge errors.
"""

from __future__ import annotations

import time

from app.core import restore
from app.engine import MaskingEngine
from app.tokenizer import count_tokens

engine = MaskingEngine(ner_enabled=False)


def _assert_not_in(sub: str, text: str) -> None:
    # Avoid pytest's difflib on large strings (which can hang).
    assert sub not in text


def _build_large_text(target_tokens: int) -> str:
    """Build a synthetic text with PII embedded, targeting ~target_tokens."""
    filler = "обычный текст без персональных данных в этом предложении "
    pii = "Клиент Иван Петров, почта ivan@example.com, телефон +7 912 345-67-89. "
    parts = []
    tokens = 0
    while tokens < target_tokens:
        parts.append(filler)
        tokens += count_tokens(filler)
        if tokens % 5000 < 20:
            parts.append(pii)
            tokens += count_tokens(pii)
    return "".join(parts)


def test_large_text_100k_tokens_round_trip():
    text = _build_large_text(100_000)
    n_tokens = count_tokens(text)
    assert n_tokens >= 100_000, f"only {n_tokens} tokens generated"

    t0 = time.perf_counter()
    res = engine.mask(text)
    mask_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    restored = restore(res.masked_text, res.mapping)
    restore_time = time.perf_counter() - t0

    # Exact round-trip: no truncation, no edge errors.
    assert restored == text
    assert res.masked is True
    # No PII remains in the masked text.
    _assert_not_in("ivan@example.com", res.masked_text)
    _assert_not_in("Иван Петров", res.masked_text)
    # Report timing.
    print(f"\n100k tokens: mask={mask_time:.2f}s restore={restore_time:.2f}s")


def test_large_text_no_truncation_length():
    text = _build_large_text(100_000)
    res = engine.mask(text)
    restored = restore(res.masked_text, res.mapping)
    assert len(restored) == len(text)


def test_large_text_pii_at_boundaries():
    # PII at the very start and end of a large text must be preserved.
    text = "почта a@b.com " + _build_large_text(50_000) + " телефон +7 912 345-67-89"
    res = engine.mask(text)
    restored = restore(res.masked_text, res.mapping)
    assert restored == text
    _assert_not_in("a@b.com", res.masked_text)
    _assert_not_in("+7 912 345-67-89", res.masked_text)


def test_100k_email_tokens_fit_both_http_directions():
    from fastapi.testclient import TestClient
    from app.main import app

    original = "a@example.com " * 100_000
    assert count_tokens(original) == 100_000
    client = TestClient(app)
    body = {"payload": original, "payload_id": "dense-100k-http"}
    response = client.post("/process", json=body)
    assert response.status_code == 200
    masked = response.json()["result"]
    assert len(masked.encode()) > 4_000_000
    assert "a@example.com" not in masked
    body["payload"] = masked
    restored = client.post("/process", json=body)
    assert restored.status_code == 200
    assert restored.json()["result"] == original
