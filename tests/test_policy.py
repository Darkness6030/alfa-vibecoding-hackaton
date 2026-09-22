"""K5a tests: system policies, two systems, forbid, revocation, immutable params.

Uses fakeredis and the demo-secure profile (two authenticated systems).
"""

from __future__ import annotations

import fakeredis
import pytest

from app.engine import MaskingEngine
from app.policy import (
    AccessDeniedError,
    PolicyConfig,
    SystemPolicy,
    UnauthorizedError,
    build_demo_secure,
    build_evaluation_open,
)
from app.state import StateStore, make_encryption_key

KEY = make_encryption_key("")


def _make_store(redis=None):
    return StateStore(
        redis=redis or fakeredis.FakeRedis(decode_responses=True),
        namespace="test",
        consumer="stand",
        ttl_seconds=900,
        max_record_bytes=1_000_000,
        encryption_key=KEY,
    )


# --- Policy config ---
def test_evaluation_open_has_open_system():
    cfg = build_evaluation_open()
    assert cfg.authenticate(None) == "stand"


def test_demo_secure_requires_api_key():
    cfg = build_demo_secure()
    with pytest.raises(UnauthorizedError):
        cfg.authenticate(None)


def test_demo_secure_authenticates_valid_key():
    cfg = build_demo_secure()
    assert cfg.authenticate("crm-secret-key") == "crm"
    assert cfg.authenticate("analytics-secret-key") == "analytics"


def test_demo_secure_rejects_invalid_key():
    cfg = build_demo_secure()
    with pytest.raises(UnauthorizedError):
        cfg.authenticate("wrong-key")


# --- Two systems with different mask_types ---
def test_two_systems_mask_different_types():
    cfg = build_demo_secure()
    crm = cfg.get("crm")
    analytics = cfg.get("analytics")
    assert "PERSON" in crm.mask_types
    assert "PERSON" not in analytics.mask_types
    assert "EMAIL" in analytics.mask_types


def test_engine_filters_by_mask_types():
    engine = MaskingEngine(mask_types={"EMAIL"})
    text = "Клиент Иван Петров, почта a@b.com"
    types = {s.type for s in engine.detect(text)}
    assert "EMAIL" in types
    assert "PERSON" not in types


# --- Forbid demasking ---
def test_analytics_cannot_demask():
    cfg = build_demo_secure()
    analytics = cfg.get("analytics")
    assert analytics.demask_allowed is False
    with pytest.raises(AccessDeniedError):
        cfg.check_demask("analytics")


def test_crm_can_demask():
    cfg = build_demo_secure()
    cfg.check_demask("crm")  # no raise


def test_demask_denied_via_store_callback():
    store = _make_store()
    engine = MaskingEngine(mask_types={"EMAIL"})
    first = store.process("id-1", "почта a@b.com", engine.mask)
    # Demask denied -> AccessDeniedError.
    with pytest.raises(AccessDeniedError):
        store.process("id-1", first.result, engine.mask, demask_allowed=lambda: False)


def test_demask_allowed_via_store_callback():
    store = _make_store()
    engine = MaskingEngine(mask_types={"EMAIL"})
    first = store.process("id-1", "почта a@b.com", engine.mask)
    back = store.process("id-1", first.result, engine.mask, demask_allowed=lambda: True)
    assert back.result == "почта a@b.com"


# --- Revocation takes effect immediately ---
def test_revocation_blocks_demask_on_existing_pair():
    store = _make_store()
    engine = MaskingEngine(mask_types={"EMAIL"})
    first = store.process("id-1", "почта a@b.com", engine.mask)
    # Initially demask allowed.
    back = store.process("id-1", first.result, engine.mask, demask_allowed=lambda: True)
    assert back.result == "почта a@b.com"
    # Revoke demask -> same pair now denied.
    with pytest.raises(AccessDeniedError):
        store.process("id-1", first.result, engine.mask, demask_allowed=lambda: False)


def test_disabled_system_blocked():
    cfg = build_demo_secure()
    cfg.systems["crm"] = SystemPolicy(
        name="crm",
        api_key="crm-secret-key",
        mask_types=frozenset({"EMAIL"}),
        demask_allowed=True,
        enabled=False,
    )
    with pytest.raises(AccessDeniedError):
        cfg.check_enabled("crm")


# --- Immutable pair transformation params ---
def test_pair_params_immutable_after_creation():
    # The mask_types used at creation are stored with the pair; changing the
    # system's mask_types does not rewrite existing pairs.
    store = _make_store()
    engine_email = MaskingEngine(mask_types={"EMAIL"})
    first = store.process("id-1", "почта a@b.com", engine_email.mask)
    assert "a@b.com" not in first.result
    # A different engine (different mask_types) still demasks the same pair.
    engine_all = MaskingEngine(mask_types={"EMAIL", "PERSON"})
    back = store.process("id-1", first.result, engine_all.mask, demask_allowed=lambda: True)
    assert back.result == "почта a@b.com"


# --- Custom policy config ---
def test_custom_policy_config():
    cfg = PolicyConfig(
        systems={
            "sys-a": SystemPolicy(
                name="sys-a", api_key="key-a", mask_types=frozenset({"EMAIL"}), demask_allowed=True
            ),
            "sys-b": SystemPolicy(
                name="sys-b", api_key="key-b", mask_types=frozenset({"PHONE"}), demask_allowed=False
            ),
        }
    )
    assert cfg.authenticate("key-a") == "sys-a"
    assert cfg.authenticate("key-b") == "sys-b"
    with pytest.raises(AccessDeniedError):
        cfg.check_demask("sys-b")