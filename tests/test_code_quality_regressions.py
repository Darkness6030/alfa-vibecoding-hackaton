"""Security and performance regressions found after the opaque jury scan."""

import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.detectors.email import EmailDetector
from app.main import app
from app.policy import AccessDeniedError, build_demo_secure
from app.engine import MaskingEngine
from app.state import StateStore, make_encryption_key
import fakeredis


def test_invalid_non_ascii_credentials_return_401():
    with TestClient(app) as client:
        response = client.post(
            "/process",
            headers={b"X-API-Key": b"\xff"},
            json={"payload": "hello", "payload_id": "non-ascii-key"},
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "unauthorized"}


def test_invalid_non_ascii_metrics_key_returns_401(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main.settings, "metrics_api_key", "synthetic-metrics-key")
    with TestClient(app) as client:
        response = client.get("/metrics", headers={b"X-Metrics-Key": b"\xff"})
        assert response.status_code == 401


def test_removed_consumer_cannot_restore_saved_pair():
    policy = build_demo_secure()
    store = StateStore(
        fakeredis.FakeRedis(decode_responses=True),
        "test",
        "crm",
        900,
        1_000_000,
        make_encryption_key(""),
    )
    engine = MaskingEngine()
    masked = store.process("removed", "mail a@b.com", engine.mask, consumer="crm")
    del policy.systems["crm"]

    def can_demask():
        policy.check_demask("crm")
        return True

    with pytest.raises(AccessDeniedError):
        store.process(
            "removed",
            masked.result,
            engine.mask,
            consumer="crm",
            demask_allowed=can_demask,
        )


def test_long_email_like_runs_finish_in_bounded_time():
    # Separate process guarantees a regression cannot hang the entire suite.
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
from app.detectors.email import EmailDetector
for text in ('a' * 1_000_000, 'a' * 500_000 + '@' + '1.' * 250_000):
    assert EmailDetector().detect(text) == []
""",
        ],
        check=True,
        timeout=5,
    )


@pytest.mark.parametrize(
    "address", ["a@b.com", "first.last+tag@sub.example.ru", "почта@пример.рф"]
)
def test_email_boundaries_preserve_values_and_offsets(address):
    text = f"Почта: <{address}>, конец."
    spans = EmailDetector().detect(text)
    assert len(spans) == 1
    assert spans[0].value == address
    assert text[spans[0].start : spans[0].end] == address


@pytest.mark.parametrize(
    "module,cls,prefix",
    [
        ("person", "PersonDetector", "клиент"),
        ("cardholder", "CardHolderDetector", "держатель карты"),
        ("address", "BirthPlaceDetector", "место рождения"),
    ],
)
def test_detector_whitespace_runs_finish_in_bounded_time(module, cls, prefix):
    # Ambiguous adjacent whitespace repetitions must not cause quadratic
    # backtracking on a long run of spaces followed by a non-matching char.
    subprocess.run(
        [
            sys.executable,
            "-c",
            f"""
from app.detectors.{module} import {cls}
text = {prefix!r} + ' ' * 16000 + '!'
assert {cls}().detect(text) == []
""",
        ],
        check=True,
        timeout=5,
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Клиент Иван Петров обратился в банк.", "Иван Петров"),
        ("Держатель карты Иван Петров", "Иван Петров"),
        ("Место рождения: г. Москва", "Москва"),
        ("Родился в г. Москва", "Москва"),
        ("Клиент: Иван Петров", "Иван Петров"),
        ("Клиент — Иван Петров", "Иван Петров"),
    ],
)
def test_detector_normal_matches_preserved(text, expected):
    from app.engine import MaskingEngine

    res = MaskingEngine().mask(text)
    assert expected not in res.masked_text
    assert res.masked is True
