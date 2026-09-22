"""Synthetic dataset for the K4a NER experiment.

Contains sentences with known PER (person) and LOC (location) entities, plus
negative examples without entities. Used to measure NER quality on a
reproducible set. All data is synthetic; no real PII.
"""

from __future__ import annotations

# (text, expected PER spans, expected LOC spans)
# Spans are (start, end) half-open character offsets.
CASES: list[tuple[str, list[tuple[int, int]], list[tuple[int, int]]]] = [
    # --- PER positive ---
    ("Иван Петров работает в банке.", [(0, 11)], []),
    ("Мария Иванова позвонила клиенту.", [(0, 13)], []),
    ("Алексей Смирнов подписал договор.", [(0, 15)], []),
    ("Документ подготовил Сергей Кузнецов.", [(20, 35)], []),
    ("Ольга Николаева ушла в отпуск.", [(0, 15)], []),
    # --- LOC positive ---
    ("Он живёт в Москве.", [], [(11, 17)]),
    ("Филиал находится в Санкт-Петербурге.", [], [(19, 35)]),
    ("Командировка в Казань.", [], [(15, 21)]),
    ("Отделение банка в Новосибирске.", [], [(18, 30)]),
    ("Адрес: город Екатеринбург.", [], [(13, 25)]),
    # --- Mixed PER + LOC ---
    ("Иван Петров из Москвы.", [(0, 11)], [(15, 21)]),
    ("Мария Иванова живёт в Казани.", [(0, 13)], [(22, 28)]),
    # --- Negative (no entities) ---
    ("Сегодня хорошая погода.", [], []),
    ("Документ подписан вчера.", [], []),
    ("Сумма операции составила 15000 рублей.", [], []),
    ("Просим подтвердить получение письма.", [], []),
]


def build_dataset() -> list[tuple[str, list[tuple[int, int]], list[tuple[int, int]]]]:
    return CASES