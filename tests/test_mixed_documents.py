"""All 17 categories must stay correct together in the realistic load corpus."""

import json
from pathlib import Path

import pytest

from app.core import TOKEN_RE, restore
from app.engine import MaskingEngine

RU = (
    "ФИО: <PERSON>; дата рождения: <BIRTH_DATE> года; место рождения: г. <BIRTH_PLACE>; "
    "гражданство: <CITIZENSHIP>; паспорт серия <PASSPORT> номер <PASSPORT>; кем выдан: <ISSUING_AUTHORITY>; "
    "код подразделения: <DIVISION_CODE>; дата выдачи: <ISSUE_DATE>; водительское удостоверение: <DRIVING_LICENSE>; "
    "домашний адрес: г. <ADDRESS>, ул. <ADDRESS>, д. <ADDRESS>, кв. <ADDRESS>; email: <EMAIL>; телефон: <PHONE>; "
    "ИНН: <INN>; карта: <CARD>; CVV: <CVV>; PIN: <PIN>; имя держателя карты: <CARD_HOLDER>."
)
EN = (
    "Full name: <PERSON>; Date of birth: <BIRTH_DATE>; Place of birth: <BIRTH_PLACE>; Citizenship: <CITIZENSHIP>; "
    "Passport series <PASSPORT> number <PASSPORT>; Issuing authority: <ISSUING_AUTHORITY>; Department code: <DIVISION_CODE>; "
    "Passport issue date: <ISSUE_DATE>; Driving licence: <DRIVING_LICENSE>; Home address: <ADDRESS> <ADDRESS> Street, <ADDRESS>; "
    "Email: <EMAIL>; Phone: <PHONE>; INN: <INN>; Card: <CARD>; CVV: <CVV>; "
    "PIN: <PIN>; Card holder name: <CARD_HOLDER>."
)
EXPECTED = [RU, EN, RU.upper(), EN.upper(), RU + " Поэт Александр Пушкин написал роман.", EN + " Author John Smith wrote a book.", RU, EN]
CORPUS = json.loads((Path(__file__).resolve().parents[1] / "benchmarks/corpus-mixed.json").read_text())


@pytest.mark.parametrize("source,expected", list(zip(CORPUS, EXPECTED, strict=True)))
def test_all_categories_in_one_document(source, expected):
    result = MaskingEngine().mask(source)
    visible = TOKEN_RE.sub(lambda match: "<" + match.group()[2:].split(":")[0] + ">", result.masked_text)
    assert visible == expected
    assert len({token[2:].split(":")[0] for token in result.mapping}) == 17
    assert restore(result.masked_text, result.mapping) == source
