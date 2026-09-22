"""K3 tests: structured categories, number context, intersection priorities.

Positive/negative/variant cases per implemented category. Categories not yet
implemented (PD01/03/05/06/09/10/17) are NOT marked here.
"""

from __future__ import annotations

import pytest

from app.core import Span, resolve_spans
from app.engine import MaskingEngine

engine = MaskingEngine()


def _types(text: str) -> set[str]:
    return {s.type for s in engine.detect(text)}


def _masked(text: str) -> str:
    return engine.mask(text).masked_text


# --- PD11 Email ---
def test_email_positive():
    assert "EMAIL" in _types("пишите на a@b.com")


def test_email_variant_unicode_domain():
    assert "EMAIL" in _types("почта иван@пример.рф")


def test_email_negative_plain_word():
    assert "EMAIL" not in _types("это не email")


# --- PD12 Phone ---
def test_phone_positive_with_context():
    assert "PHONE" in _types("телефон +7 912 345-67-89")


def test_phone_positive_8_prefix():
    assert "PHONE" in _types("позвони 8 912 345 67 89")


def test_phone_negative_without_context():
    assert "PHONE" not in _types("номер 89123456789 в тексте")


# --- PD13 INN ---
def test_inn_positive():
    assert "INN" in _types("ИНН 7707083893")


def test_inn_positive_12_digit():
    assert "INN" in _types("ИНН 500100732259")


def test_inn_negative_without_keyword():
    assert "INN" not in _types("число 7707083893 просто")


# --- PD14 Card number ---
def test_card_positive_luhn():
    # 4111111111111111 is a valid Luhn test card.
    assert "CARD" in _types("карта 4111111111111111")


def test_card_positive_grouped():
    assert "CARD" in _types("карта 4111 1111 1111 1111")


def test_card_negative_invalid_luhn_no_context():
    assert "CARD" not in _types("число 1234567890123456")


# --- PD15 CVV ---
def test_cvv_positive():
    assert "CVV" in _types("cvv 123")


def test_cvv_negative_without_context():
    assert "CVV" not in _types("код 123")


# --- PD16 PIN ---
def test_pin_positive():
    assert "PIN" in _types("пин 1234")


def test_pin_negative_without_context():
    assert "PIN" not in _types("число 1234")


# --- PD04 Passport ---
def test_passport_positive():
    assert "PASSPORT" in _types("паспорт 4509 123456")


def test_passport_negative_without_context():
    assert "PASSPORT" not in _types("число 4509 123456")


# --- PD07 Division code ---
def test_division_code_positive():
    assert "DIVISION_CODE" in _types("код подразделения 770-001")


def test_division_code_negative_without_context():
    assert "DIVISION_CODE" not in _types("770-001")


# --- PD02 Birth date ---
def test_birth_date_positive():
    assert "BIRTH_DATE" in _types("дата рождения 15.03.1990")


def test_birth_date_negative_arbitrary():
    assert "BIRTH_DATE" not in _types("встреча 15.03.1990")


# --- PD08 Issue date ---
def test_issue_date_positive():
    assert "ISSUE_DATE" in _types("дата выдачи 20.04.2015")


def test_issue_date_negative_arbitrary():
    assert "ISSUE_DATE" not in _types("встреча 20.04.2015")


# --- Intersection priorities ---
def test_priority_higher_wins_on_overlap():
    # A card number (priority 50) overlapping a generic lower-priority span.
    spans = [
        Span(0, 16, "LOW", "4111111111111111", priority=10),
        Span(0, 16, "CARD", "4111111111111111", priority=50),
    ]
    resolved = resolve_spans(spans)
    assert len(resolved) == 1
    assert resolved[0].type == "CARD"


def test_priority_equal_earliest_start_wins():
    spans = [
        Span(3, 8, "B", "34567"),
        Span(0, 5, "A", "01234"),
    ]
    resolved = resolve_spans(spans)
    assert len(resolved) == 1
    assert resolved[0].type == "A"


def test_card_overlaps_phone_priority():
    # Card number should win over a phone-like span when they overlap.
    text = "карта 4111111111111111"
    types = _types(text)
    assert "CARD" in types


def test_round_trip_with_multiple_categories():
    original = "ИНН 7707083893, телефон +7 912 345-67-89, карта 4111111111111111"
    res = engine.mask(original)
    from app.core import restore

    assert restore(res.masked_text, res.mapping) == original
    assert res.masked is True


def test_no_pii_unchanged():
    original = "просто текст без персональных данных"
    res = engine.mask(original)
    assert res.masked is False
    assert res.masked_text == original


def test_keyword_from_unrelated_clause_does_not_leak():
    # "пин" belongs to "пин 1234", not to "паспорт 4509 123456".
    text = "пин 1234, паспорт 4509 123456"
    types = _types(text)
    assert "PASSPORT" in types
    assert "PIN" in types
    # The passport series must not be swallowed by the PIN detector.
    res = engine.mask(text)
    assert "4509 123456" not in res.masked_text
    assert "{{PASSPORT:" in res.masked_text