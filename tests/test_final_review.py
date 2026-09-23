"""Regression cases from the final requirements review."""

import pytest

from app.core import TOKEN_RE, restore
from app.engine import MaskingEngine


@pytest.mark.parametrize("source,expected", [
    ("Клиент Иван\u00a0Петров", "Клиент <PERSON>"),
    ("Customer Anne\u202fSmith", "Customer <PERSON>"),
    ("ФИО: Иванов\u00a0Иван\u202fИванович", "ФИО: <PERSON>"),
    ("Улица: 1-я Тверская-Ямская", "Улица: <ADDRESS>"),
    ("Street: 2nd Avenue", "Street: <ADDRESS>"),
    ("Город: Нижний\u00a0Новгород", "Город: <ADDRESS>"),
    ("First name: John; Last name: Smith", "First name: <PERSON>; Last name: <PERSON>"),
    ("Имя: Иван; Фамилия: Петров; Отчество: Иванович", "Имя: <PERSON>; Фамилия: <PERSON>; Отчество: <PERSON>"),
    ("Имя: Иван Петров", "Имя: <PERSON>"),
    ("Card holder name: JOHN SMITH", "Card holder name: <CARD_HOLDER>"),
    ("Имя держателя карты: ИВАН ПЕТРОВ", "Имя держателя карты: <CARD_HOLDER>"),
    ("Адрес офиса: г. Москва, ул. Ленина, д. 5", "Адрес офиса: г. Москва, ул. Ленина, д. 5"),
    ("Адрес офиса: г. Москва, ул. Ленина, д. 5; домашний адрес клиента: г. Тула, ул. Мира, д. 7", "Адрес офиса: г. Москва, ул. Ленина, д. 5; домашний адрес клиента: г. <ADDRESS>, ул. <ADDRESS>, д. <ADDRESS>"),
])
@pytest.mark.parametrize("uppercase", [False, True])
def test_final_review_boundaries(source, expected, uppercase):
    if uppercase:
        source, expected = source.upper(), expected.upper()
    result = MaskingEngine().mask(source)
    readable = TOKEN_RE.sub(lambda match: "<" + match.group()[2:].split(":")[0] + ">", result.masked_text)
    assert readable == expected
    assert restore(result.masked_text, result.mapping) == source
