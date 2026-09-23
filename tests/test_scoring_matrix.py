"""Independent mixed-category acceptance examples derived from the full spec."""
import pytest
from app.core import restore
from app.engine import MaskingEngine
from tests.test_bilingual import readable


CASES = [
 ('Клиент Александр Пушкин', 'Клиент <PERSON>'),
 ('Поэт Александр Пушкин', 'Поэт Александр Пушкин'),
 ('Дата рождения: 03.15.1990', 'Дата рождения: <BIRTH_DATE>'),
 ('Дата рождения: 1990.15.03', 'Дата рождения: <BIRTH_DATE>'),
 ('Место рождения: г. Нижний Новгород', 'Место рождения: г. <BIRTH_PLACE>'),
 ('паспорт серия 45 09 номер', 'паспорт серия <PASSPORT> номер'),
 ('г. Москва, ул. Маросейка, д. 5', 'г. <ADDRESS>, ул. <ADDRESS>, д. <ADDRESS>'),
 ('Гражданство: Республика Беларусь', 'Гражданство: <CITIZENSHIP>'),
 ('Кем выдан: ОВД Центрального района', 'Кем выдан: <ISSUING_AUTHORITY>'),
 ('Код подразделения: 770-001', 'Код подразделения: <DIVISION_CODE>'),
 ('Дата выдачи: 2020.15.03', 'Дата выдачи: <ISSUE_DATE>'),
 ('Водительское удостоверение: 77 11 123456', 'Водительское удостоверение: <DRIVING_LICENSE>'),
 ('Email: alice@example.org', 'Email: <EMAIL>'),
 ('Телефон: 8 (912) 345-67-89', 'Телефон: <PHONE>'),
 ('ИНН: 7707083893', 'ИНН: <INN>'),
 ('Карта: 4111-1111-1111-1111', 'Карта: <CARD>'),
 ('CVV: 123', 'CVV: <CVV>'),
 ('ПИН: 1234', 'ПИН: <PIN>'),
 ('Держатель карты: ИВАН ПЕТРОВ', 'Держатель карты: <CARD_HOLDER>'),
 ('Адрес отделения банка: г. Москва, ул. Ленина, д. 5', 'Адрес отделения банка: г. Москва, ул. Ленина, д. 5'),
]


@pytest.mark.parametrize('text,expected', CASES)
def test_spec_acceptance(text, expected):
    result = MaskingEngine().mask(text)
    assert readable(result) == expected
    assert restore(result.masked_text, result.mapping) == text
