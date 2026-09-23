"""RU/EN/mixed behavior and previously uncovered release regressions."""

import subprocess
import sys

import pytest
from app.core import TOKEN_RE, restore
from app.engine import MaskingEngine


def readable(result):
    return TOKEN_RE.sub(
        lambda m: "<" + m.group()[2:].split(":")[0] + ">", result.masked_text
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("паспорт выдан 12.03.2020", "паспорт выдан <ISSUE_DATE>"),
        ("паспорт выдан 2020-03-12", "паспорт выдан <ISSUE_DATE>"),
        ("ВУ выдано 12.03.2020", "ВУ выдано <ISSUE_DATE>"),
        ("номер паспорта 123456", "номер паспорта <PASSPORT>"),
        ("паспорт серия 4509   ", "паспорт серия <PASSPORT>   "),
        (
            "Passport series 45 09 number 123456",
            "Passport series <PASSPORT> number <PASSPORT>",
        ),
        ("Passport number: 123456", "Passport number: <PASSPORT>"),
        (
            "Driving licence series 77 11 number 123456",
            "Driving licence series <DRIVING_LICENSE> number <DRIVING_LICENSE>",
        ),
        ("Customer John Smith", "Customer <PERSON>"),
        ("Customer: Anne-Marie O'Connor", "Customer: <PERSON>"),
        ("Full name: José García", "Full name: <PERSON>"),
        ("Клиент John Smith", "Клиент <PERSON>"),
        ("Date of birth: 15 March 1990", "Date of birth: <BIRTH_DATE>"),
        ("DOB: March 15, 1990", "DOB: <BIRTH_DATE>"),
        ("DOB: 1990-03-15", "DOB: <BIRTH_DATE>"),
        ("Place of birth: New York", "Place of birth: <BIRTH_PLACE>"),
        ("Citizenship: Russian Federation", "Citizenship: <CITIZENSHIP>"),
        ("Гражданство: Германия", "Гражданство: <CITIZENSHIP>"),
        (
            "Passport issued by: Ministry of Internal Affairs",
            "Passport issued by: <ISSUING_AUTHORITY>",
        ),
        ("Department code: 770-001", "Department code: <DIVISION_CODE>"),
        ("Passport issue date: 12.03.2020", "Passport issue date: <ISSUE_DATE>"),
        (
            "Home address: 221B Baker Street, London",
            "Home address: <ADDRESS> <ADDRESS> Street, <ADDRESS>",
        ),
        (
            "Адрес: г. Нижний Новгород, ул. Большая Покровская, д. 5",
            "Адрес: г. <ADDRESS>, ул. <ADDRESS>, д. <ADDRESS>",
        ),
        ("Клиент проживает в Москве", "Клиент проживает в <ADDRESS>"),
        ("Email: john.smith@example.com", "Email: <EMAIL>"),
        ("Phone: +1 (202) 555-0147", "Phone: <PHONE>"),
        ("Telephone: +44 20 7946 0958", "Telephone: <PHONE>"),
        ("INN: 7707083893", "INN: <INN>"),
        (
            "Taxpayer identification number: 7707083893",
            "Taxpayer identification number: <INN>",
        ),
        ("Card number: 4111 1111 1111 1111", "Card number: <CARD>"),
        ("CVV: 123", "CVV: <CVV>"),
        ("PIN: 1234", "PIN: <PIN>"),
        ("Card holder: ANNE-MARIE O'CONNOR", "Card holder: <CARD_HOLDER>"),
    ],
)
@pytest.mark.parametrize("uppercase", [False, True])
def test_bilingual_values_types_and_boundaries(text, expected, uppercase):
    if uppercase:
        text, expected = text.upper(), expected.upper()
    result = MaskingEngine().mask(text)
    assert readable(result) == expected
    assert restore(result.masked_text, result.mapping) == text


@pytest.mark.parametrize(
    "text",
    [
        "Паспорт изделия, год выпуска 2020",
        "Product passport issued in 2020",
        "Author John Smith wrote a novel.",
        "Bank branch address: 221B Baker Street, London",
        "Report date: 15 March 1990",
        "Order number: 123456",
        "Product series 4509",
        "Bank branch: city: London",
        "Адрес отделения банка: город: Москва",
    ],
)
def test_nonpersonal_context_is_unchanged(text):
    assert MaskingEngine().mask(text).masked_text == text


@pytest.mark.parametrize(
    "module,detector,prefix",
    [
        ("citizenship", "CitizenshipDetector", "гражданство"),
        ("issuing", "IssuingAuthorityDetector", "кем выдан"),
    ],
)
def test_unmatched_whitespace_is_bounded(module, detector, prefix):
    code = f'from app.detectors.{module} import {detector}; assert not {detector}().detect({prefix!r}+" "*100_000+"!")'
    subprocess.run([sys.executable, "-c", code], check=True, timeout=3)


def test_mixed_language_proxy_masks_all_fields_and_logs_types(caplog):
    import logging
    from app.proxy import ProxyService
    from app.llm import MockLLM

    text = "Customer José García; дата рождения 15 марта 1990 года; Phone: +44 20 7946 0958; Email: jose@example.com"
    with caplog.at_level(logging.INFO, logger="alfagen"):
        result = ProxyService(MaskingEngine(), MockLLM()).run(text)
    for secret in (
        "José García",
        "15 марта 1990",
        "+44 20 7946 0958",
        "jose@example.com",
    ):
        assert secret not in result.masked_input
        assert secret not in result.llm_response
        assert secret in result.restored_response
        assert secret not in caplog.text
    assert "stage=proxy_types types=" in caplog.text
    assert "stage=detect" in caplog.text
    assert "stage=restore" in caplog.text


def test_issuing_authority_keeps_internal_prepositions_and_dots():
    text = "Паспорт выдан УФМС России по г. Москве; дата выдачи 12.03.2020"
    result = MaskingEngine().mask(text)
    assert (
        readable(result)
        == "Паспорт выдан <ISSUING_AUTHORITY>; дата выдачи <ISSUE_DATE>"
    )
    assert restore(result.masked_text, result.mapping) == text


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Паспорт № 123456", "Паспорт № <PASSPORT>"),
        ("Passport No. 123456", "Passport No. <PASSPORT>"),
    ],
)
def test_independent_document_number_markers(text, expected):
    result = MaskingEngine().mask(text)
    assert readable(result) == expected
    assert restore(result.masked_text, result.mapping) == text


def test_unlabelled_english_address_words_are_not_personal_fields():
    text = "We discussed house prices and city planning."
    assert MaskingEngine().mask(text).masked_text == text
