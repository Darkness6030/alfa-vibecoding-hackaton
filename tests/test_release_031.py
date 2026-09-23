"""Complete compound address values and labelled initials without overmasking."""
import pytest
from app.engine import MaskingEngine
from app.core import restore
from tests.test_bilingual import readable


@pytest.mark.parametrize('text,expected', [
    ('Адрес: г. Москва, ул. Ленина, д. 5, корп. 2, кв. 15', 'Адрес: г. <ADDRESS>, ул. <ADDRESS>, д. <ADDRESS>, корп. <ADDRESS>, кв. <ADDRESS>'),
    ('Дом: 12/3', 'Дом: <ADDRESS>'),
    ('Адрес: д. 12/3, стр. 4', 'Адрес: д. <ADDRESS>, стр. <ADDRESS>'),
    ('Postcode: SW1A 1AA', 'Postcode: <ADDRESS>'),
    ('Postal code: 02139-4307', 'Postal code: <ADDRESS>'),
    ('Postal code: K1A 0B1', 'Postal code: <ADDRESS>'),
    ('ФИО: Иванов И. И.', 'ФИО: <PERSON>'),
    ('ФИО: И. И. Иванов', 'ФИО: <PERSON>'),
    ('Full name: J. R. Smith', 'Full name: <PERSON>'),
    ('Клиент Иванов И.И., email a@example.com', 'Клиент <PERSON>, email <EMAIL>'),
])
@pytest.mark.parametrize('uppercase', [False, True])
def test_complete_values(text, expected, uppercase):
    if uppercase:
        text, expected = text.upper(), expected.upper()
    result = MaskingEngine().mask(text)
    assert readable(result) == expected
    assert restore(result.masked_text, result.mapping) == text


@pytest.mark.parametrize('text', [
    'Bank branch postcode: SW1A 1AA',
    'Адрес отделения банка: д. 12/3, корп. 2',
    'Корпус исследования состоит из текстов.',
    'Author J. R. Smith wrote a novel.',
    'Клиент обратился в банк.',
])
def test_negative_context(text):
    assert MaskingEngine().mask(text).masked_text == text


def test_overload_retry_preserves_pair_in_both_directions(monkeypatch):
    import threading
    from fastapi.testclient import TestClient
    import app.main as main

    client = TestClient(main.app)
    original = 'ФИО: Иванов И. И.; Postcode: SW1A 1AA'
    data = {'payload': original, 'payload_id': 'retry-compound'}
    for direction in ('mask', 'restore'):
        with monkeypatch.context() as overloaded:
            overloaded.setattr(main, '_semaphore', threading.BoundedSemaphore(0))
            response = client.post('/process', json=data)
            assert response.status_code == 429
            assert response.headers['Retry-After'] == '1'
        # Model the next attempt after capacity is available; no wall-clock sleep needed.
        response = client.post('/process', json=data)
        assert response.status_code == 200
        result = response.json()['result']
        assert client.post('/process', json=data).json()['result'] == result
        if direction == 'mask':
            assert 'Иванов' not in result and 'SW1A' not in result
            data['payload'] = result
        else:
            assert result == original
