"""Isolated synthetic credentials and in-memory transport state for each test."""

import os
from cryptography.fernet import Fernet

os.environ["ALFAGEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["ALFAGEN_CRM_API_KEY"] = "test-crm-only"
os.environ["ALFAGEN_ANALYTICS_API_KEY"] = "test-analytics-only"
import pytest
import fakeredis


@pytest.fixture(autouse=True)
def isolated_http(monkeypatch):
    import app.main as main
    from app.policy import build_evaluation_open
    from app.state import StateStore, make_encryption_key

    monkeypatch.setattr(main, "policy", build_evaluation_open())
    monkeypatch.setattr(
        main,
        "store",
        StateStore(
            fakeredis.FakeRedis(decode_responses=True),
            "test",
            "stand",
            900,
            16_000_000,
            make_encryption_key(""),
        ),
    )
