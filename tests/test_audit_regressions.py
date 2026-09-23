"""Regressions for issues independently reproduced during the code audit."""

import json
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
import app.main as main
from app.engine import MaskingEngine
from app.core import restore
from app.state import ConflictError, StorageError
from app.policy import load_policy


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.mark.parametrize(
    "payload",
    [
        {"payload": {"secret": "PRIVATE_TEST_VALUE"}, "payload_id": "x"},
        {"payload": "PRIVATE_TEST_VALUE"},
        {"payload": "text", "payload_id": ["PRIVATE_TEST_VALUE"]},
    ],
)
def test_validation_never_reflects_input(client, payload):
    r = client.post("/process", json=payload)
    assert r.status_code == 422
    assert "PRIVATE_TEST_VALUE" not in r.text


def test_open_stand_does_not_open_proxy_or_metrics(client):
    assert (
        client.post(
            "/proxy", json={"payload": "a@b.com", "payload_id": "a"}
        ).status_code
        == 401
    )
    assert client.get("/metrics").status_code == 401


def test_tenants_cannot_read_each_others_mapping(client, monkeypatch):
    from app.policy import SystemPolicy

    main.policy.systems["other"] = SystemPolicy(
        "other", "test-other", demask_allowed=True
    )
    req = {"payload": "a@b.com", "payload_id": "same"}
    masked = client.post(
        "/process", json=req, headers={"X-API-Key": "test-crm-only"}
    ).json()["result"]
    r = client.post(
        "/process", json={**req, "payload": masked}, headers={"X-API-Key": "test-other"}
    )
    assert r.status_code == 409 and "a@b.com" not in r.text
    req["payload"] = "different@sample.org"
    assert (
        client.post(
            "/process", json=req, headers={"X-API-Key": "test-other"}
        ).status_code
        == 200
    )


def test_retries_skip_detector_and_keep_ttl():
    calls = []

    def detector(text):
        calls.append(text)
        return MaskingEngine().mask(text)

    first = main.store.process("r", "a@b.com", detector)
    for value in ("a@b.com", first.result, first.result):
        main.store.process("r", value, detector)
    assert calls == ["a@b.com"]


def test_expired_mask_does_not_become_new_original():
    first = main.store.process("r", "a@b.com", MaskingEngine().mask)
    main.store._redis.flushall()
    with pytest.raises(ConflictError):
        main.store.process("r", first.result, MaskingEngine().mask)


def test_actual_encrypted_record_limit():
    main.store._max_record_bytes = 500
    with pytest.raises(StorageError):
        main.store.process("r", "a@b.com " * 30, MaskingEngine().mask)
    assert main.store._redis.dbsize() == 0


def test_revocation_is_checked_on_existing_pair(client):
    h = {"X-API-Key": "test-crm-only"}
    req = {"payload": "a@b.com", "payload_id": "r"}
    first = client.post("/process", json=req, headers=h).json()["result"]
    main.policy.systems["crm"] = replace(main.policy.get("crm"), demask_allowed=False)
    assert (
        client.post("/process", json={**req, "payload": first}, headers=h).status_code
        == 403
    )


@pytest.mark.parametrize(
    "text, secret, type_",
    [
        ("КЛИЕНТ ИВАН ПЕТРОВ", "ИВАН ПЕТРОВ", "PERSON"),
        ("клиент иван петров", "иван петров", "PERSON"),
        ("ФИО: Сидоров Семён Петрович", "Сидоров Семён Петрович", "PERSON"),
        ("Дата рождения 15 марта 1990 года", "15 марта 1990", "BIRTH_DATE"),
        ("Дата выдачи 2015-20-04", "2015-20-04", "ISSUE_DATE"),
        ("Паспорт серия 45 09 номер 123456", "123456", "PASSPORT"),
        ("ВУ серия 77 12 номер 345678", "345678", "DRIVING_LICENSE"),
        ("Держатель карты IVAN PETROV", "IVAN PETROV", "CARD_HOLDER"),
        (
            "Адрес: г. москва, ул. ленина, д. 5",
            "москва",
            "ADDRESS",
        ),
        (
            "Паспорт выдан ОВД района Тверской",
            "ОВД района Тверской",
            "ISSUING_AUTHORITY",
        ),
        ("Гражданство: Российская Федерация", "Российская Федерация", "CITIZENSHIP"),
        ("Место рождения: Москва", "Москва", "BIRTH_PLACE"),
        ("Связь: +7 912 345-67-89", "+7 912 345-67-89", "PHONE"),
        ("страна: Россия", "Россия", "ADDRESS"),
    ],
)
def test_variants_exact_mask_and_round_trip(text, secret, type_):
    e = MaskingEngine()
    spans = e.detect(text)
    assert any(s.value == secret and s.type == type_ for s in spans)
    out = e.mask(text)
    assert secret not in out.masked_text
    assert restore(out.masked_text, out.mapping) == text


def test_public_context_does_not_hide_customer_same_name():
    text = "Поэт Александр Пушкин. Клиент Александр Пушкин, паспорт 4509 123456"
    out = MaskingEngine().mask(text)
    assert out.masked_text.startswith("Поэт Александр Пушкин.")
    assert out.masked_text.count("Александр Пушкин") == 1


def test_proxy_uses_policy_and_labels_mock(client):
    r = client.post(
        "/proxy",
        json={"payload": "КЛИЕНТ ИВАН ПЕТРОВ, a@b.com", "payload_id": "x"},
        headers={"X-API-Key": "test-crm-only"},
    )
    assert r.status_code == 200
    b = r.json()
    assert b["llm_mode"] == "mock" and "a@b.com" not in b["masked_input"]
    assert "ИВАН ПЕТРОВ" not in b["masked_input"]
    assert "a@b.com" in b["restored_response"]


def test_new_pii_from_adapter_is_masked():
    from app.proxy import ProxyService

    class Adapter:
        def generate(self, text):
            return text + " новая почта new@sample.org"

    b = ProxyService(MaskingEngine(), Adapter()).run("a@b.com")
    assert "new@sample.org" not in b.llm_response
    assert "new@sample.org" not in b.restored_response
    assert "a@b.com" in b.restored_response


def test_restore_does_not_recursively_replace_inserted_values():
    a = "{{EMAIL:" + "a" * 16 + "}}"
    b = "{{EMAIL:" + "b" * 16 + "}}"
    assert restore(a + " " + b, {a: b, b: "value"}) == b + " value"


def test_body_limit(client, monkeypatch):
    monkeypatch.setattr(main.settings, "max_body_bytes", 128)
    r = client.post("/process", json={"payload": "x" * 200, "payload_id": "x"})
    assert r.status_code == 413


def test_redaction_and_combination_modes():
    e = MaskingEngine(mask_mode="redact")
    assert e.mask("a@b.com").masked_text == "*******"
    e = MaskingEngine(combinations=(("PIN", ("CARD",)),))
    assert e.mask("ПИН 1234").masked_text == "ПИН 1234"
    assert "1234" not in e.mask("ПИН 1234, карта 4111111111111111").masked_text


def test_custom_rule_from_json(tmp_path):
    f = tmp_path / "policy.json"
    f.write_text(
        json.dumps(
            {
                "open_system": "stand",
                "systems": {"stand": {}},
                "custom_patterns": [{"type": "CONTRACT", "pattern": "TEST-[0-9]{4}"}],
            }
        )
    )
    p = load_policy(str(f), "evaluation-open")
    e = MaskingEngine(custom_patterns=p.custom_patterns)
    assert "TEST-1234" not in e.mask("Документ TEST-1234").masked_text


def test_types_logged_and_tps_exported(client, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="alfagen"):
        client.post(
            "/process", json={"payload": "private@sample.org", "payload_id": "r"}
        )
    assert "types=EMAIL" in caplog.text
    assert "private@sample.org" not in caplog.text
    metrics = client.get("/metrics", headers={"X-API-Key": "test-crm-only"}).text
    assert "alfagen_input_tokens_total" in metrics


def test_driving_series_is_not_classified_as_passport():
    from app.core import resolve_spans

    assert {
        s.type
        for s in resolve_spans(MaskingEngine().detect("ВУ серия 77 12 номер 345678"))
    } == {"DRIVING_LICENSE"}


def test_bank_address_in_genitive_is_public():
    text = "Адрес отделения банка: г. Москва, ул. Ленина, д. 5"
    assert MaskingEngine().mask(text).masked_text == text


def test_hot_reload_revokes_existing_pair(client, monkeypatch, tmp_path):
    import os

    f = tmp_path / "policy.json"
    data = {
        "systems": {
            "stand": {"demask_allowed": True},
            "crm": {"api_key_env": "ALFAGEN_CRM_API_KEY", "demask_allowed": True},
        }
    }
    f.write_text(json.dumps(data))
    monkeypatch.setattr(main.settings, "policy_file", str(f))
    monkeypatch.setattr(main, "_policy_stamp", None)
    h = {"X-API-Key": "test-crm-only"}
    first = client.post(
        "/process", json={"payload": "a@b.com", "payload_id": "r"}, headers=h
    ).json()["result"]
    data["systems"]["crm"]["enabled"] = False
    f.write_text(json.dumps(data))
    os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 1_000_000))
    assert (
        client.post(
            "/process", json={"payload": first, "payload_id": "r"}, headers=h
        ).status_code
        == 403
    )


def test_config_invalid_boolean_fails_closed(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"systems": {"stand": {"enabled": "false"}}}))
    with pytest.raises(ValueError):
        load_policy(str(f), "evaluation-open")
