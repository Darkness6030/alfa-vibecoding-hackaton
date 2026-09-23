"""K8 tests: complex negative cases (should NOT be flagged as PII).

These verify that the detectors do not over-flag ordinary text, famous names in
literary context, bank branch addresses, and numbers without personal context.
"""

from __future__ import annotations

from app.engine import MaskingEngine

engine = MaskingEngine(ner_enabled=False)


def _types(text: str) -> set[str]:
    return {s.type for s in engine.detect(text)}


def test_famous_poet_not_pii():
    assert "PERSON" not in _types(
        "Поэт Александр Пушкин написал роман «Евгений Онегин»."
    )


def test_famous_writer_not_pii():
    assert "PERSON" not in _types("Писатель Лев Толстой — автор «Войны и мира».")


def test_bank_branch_address_not_pii():
    # Bank branch address is not personal data (F01).
    assert "ADDRESS" not in _types(
        "Отделение банка находится по адресу г. Москва, ул. Ленина, д. 5"
    )


def test_ordinary_number_not_inn():
    assert "INN" not in _types("Сумма операции составила 7707083893 рублей")


def test_ordinary_number_not_card():
    assert "CARD" not in _types("Код заказа 1234567890123456")


def test_ordinary_date_not_birth():
    assert "BIRTH_DATE" not in _types("Срок действия договора до 15.03.1990")


def test_ordinary_date_not_issue():
    assert "ISSUE_DATE" not in _types("Планёрка назначена на 20.04.2015")


def test_phone_without_context_not_pii():
    assert "PHONE" not in _types("Номер заявки 89123456789")


def test_cvv_without_card_context_not_pii():
    assert "CVV" not in _types("Код 123")


def test_pin_without_context_not_pii():
    assert "PIN" not in _types("Число 1234")


def test_passport_number_without_context_not_pii():
    assert "PASSPORT" not in _types("Артикул 4509 123456")


def test_citizenship_without_context_not_pii():
    assert "CITIZENSHIP" not in _types("Российская компания зарегистрирована в Москве")


def test_issuing_authority_without_context_not_pii():
    assert "ISSUING_AUTHORITY" not in _types("ОВД района проводит ремонт")


def test_driving_license_without_context_not_pii():
    assert "DRIVING_LICENSE" not in _types("Номер 7712 345678 в реестре")


def test_card_holder_without_context_not_pii():
    assert "CARD_HOLDER" not in _types("Иван Петров работает в банке")


def test_division_code_without_context_not_pii():
    assert "DIVISION_CODE" not in _types("770-001")


def test_negative_cases_do_not_mask():
    text = "Поэт Александр Пушкин написал роман. Сумма 7707083893 рублей."
    res = engine.mask(text)
    assert res.masked is False
    assert res.masked_text == text
