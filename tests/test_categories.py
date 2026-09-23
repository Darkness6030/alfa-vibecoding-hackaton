"""K4b tests: all PD01-PD17 categories represented + context exceptions.

Each category has a positive and a negative case. Context exceptions (F01):
a famous name in a literary context is not PII.
"""

from __future__ import annotations

from app.engine import MaskingEngine

# NER disabled so tests run without natasha installed.
engine = MaskingEngine(ner_enabled=False)


def _types(text: str) -> set[str]:
    return {s.type for s in engine.detect(text)}


# --- PD01 ФИО ---
def test_pd01_person_positive():
    assert "PERSON" in _types("Клиент Иван Петров обратился в банк.")


def test_pd01_person_negative_literary():
    # Famous name in literary context is not PII (F01).
    assert "PERSON" not in _types("Поэт Александр Пушкин написал роман.")


# --- PD02 Дата рождения ---
def test_pd02_birth_date_positive():
    assert "BIRTH_DATE" in _types("Дата рождения 15.03.1990")


def test_pd02_birth_date_negative_arbitrary():
    assert "BIRTH_DATE" not in _types("Встреча 15.03.1990")


# --- PD03 Место рождения ---
def test_pd03_birth_place_positive():
    assert "BIRTH_PLACE" in _types("Родился в г. Москва")


def test_pd03_birth_place_negative():
    assert "BIRTH_PLACE" not in _types("Командировка в г. Москва")


# --- PD04 Паспорт ---
def test_pd04_passport_positive():
    assert "PASSPORT" in _types("Паспорт 4509 123456")


def test_pd04_passport_negative():
    assert "PASSPORT" not in _types("Число 4509 123456")


# --- PD05 Гражданство ---
def test_pd05_citizenship_positive():
    assert "CITIZENSHIP" in _types("Гражданство Российская")


def test_pd05_citizenship_negative():
    assert "CITIZENSHIP" not in _types("Российская компания")


# --- PD06 Орган выдачи ---
def test_pd06_issuing_authority_positive():
    assert "ISSUING_AUTHORITY" in _types("Паспорт выдан ОВД района")


def test_pd06_issuing_authority_negative():
    assert "ISSUING_AUTHORITY" not in _types("ОВД района работает")


# --- PD07 Код подразделения ---
def test_pd07_division_code_positive():
    assert "DIVISION_CODE" in _types("Код подразделения 770-001")


def test_pd07_division_code_negative():
    assert "DIVISION_CODE" not in _types("770-001")


# --- PD08 Дата выдачи ---
def test_pd08_issue_date_positive():
    assert "ISSUE_DATE" in _types("Дата выдачи 20.04.2015")


def test_pd08_issue_date_negative():
    assert "ISSUE_DATE" not in _types("Встреча 20.04.2015")


# --- PD09 Серия/номер ВУ ---
def test_pd09_driving_license_positive():
    assert "DRIVING_LICENSE" in _types("Водительское удостоверение 7712 345678")


def test_pd09_driving_license_negative():
    assert "DRIVING_LICENSE" not in _types("Число 7712 345678")


# --- PD10 Адрес ---
def test_pd10_address_positive():
    assert "ADDRESS" in _types("Адрес: г. Москва, ул. Ленина, д. 5")


def test_pd10_address_negative():
    # A bare city mention without address structure is not an address.
    assert "ADDRESS" not in _types("Командировка в Москву")


def test_pd10_address_standalone_structured():
    # A structured multi-component address is masked even without "Адрес:".
    assert "ADDRESS" in _types("г. Москва, ул. Маросейка, д. 5")


# --- PD11 Email ---
def test_pd11_email_positive():
    assert "EMAIL" in _types("Почта a@b.com")


def test_pd11_email_negative():
    assert "EMAIL" not in _types("Это не email")


# --- PD12 Телефон ---
def test_pd12_phone_positive():
    assert "PHONE" in _types("Телефон +7 912 345-67-89")


def test_pd12_phone_negative():
    assert "PHONE" not in _types("Номер 89123456789")


# --- PD13 ИНН ---
def test_pd13_inn_positive():
    assert "INN" in _types("ИНН 7707083893")


def test_pd13_inn_negative():
    assert "INN" not in _types("Число 7707083893")


# --- PD14 Номер карты ---
def test_pd14_card_positive():
    assert "CARD" in _types("Карта 4111111111111111")


def test_pd14_card_negative():
    assert "CARD" not in _types("Число 1234567890123456")


# --- PD15 CVV ---
def test_pd15_cvv_positive():
    assert "CVV" in _types("cvv 123")


def test_pd15_cvv_negative():
    assert "CVV" not in _types("Код 123")


# --- PD16 ПИН ---
def test_pd16_pin_positive():
    assert "PIN" in _types("Пин 1234")


def test_pd16_pin_negative():
    assert "PIN" not in _types("Число 1234")


# --- PD17 Имя держателя карты ---
def test_pd17_card_holder_positive():
    assert "CARD_HOLDER" in _types("Держатель карты Иван Петров")


def test_pd17_card_holder_negative():
    assert "CARD_HOLDER" not in _types("Иван Петров работает")


# --- All 17 categories present ---
def test_all_17_categories_represented():
    text = (
        "Клиент Иван Петров, дата рождения 15.03.1990, родился в г. Москва, "
        "паспорт 4509 123456, гражданство Российская, выдан ОВД района, "
        "код подразделения 770-001, дата выдачи 20.04.2015, "
        "водительское 7712 345678, адрес г. Москва ул. Ленина д. 5, "
        "почта a@b.com, телефон +7 912 345-67-89, ИНН 7707083893, "
        "карта 4111111111111111, cvv 123, пин 1234, держатель карты Иван Петров"
    )
    types = _types(text)
    expected = {
        "PERSON",
        "BIRTH_DATE",
        "BIRTH_PLACE",
        "PASSPORT",
        "CITIZENSHIP",
        "ISSUING_AUTHORITY",
        "DIVISION_CODE",
        "ISSUE_DATE",
        "DRIVING_LICENSE",
        "ADDRESS",
        "EMAIL",
        "PHONE",
        "INN",
        "CARD",
        "CVV",
        "PIN",
        "CARD_HOLDER",
    }
    missing = expected - types
    assert not missing, f"missing categories: {missing}"
