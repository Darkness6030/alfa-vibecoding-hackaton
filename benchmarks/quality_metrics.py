"""K8 quality metrics: precision/recall/F1 on a synthetic set.

Runs the engine over a synthetic set with known PII spans and reports
per-category and overall precision/recall/F1. This is a local diagnostic, not
the official evaluator metric.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import resolve_spans
from app.engine import MaskingEngine

# (text, expected_types) where expected_types is a list of (type, start, end).
CASES: list[tuple[str, list[tuple[str, int, int]]]] = [
    ("Клиент Иван Петров обратился в банк.", [("PERSON", 7, 18)]),
    ("Дата рождения 15.03.1990", [("BIRTH_DATE", 14, 24)]),
    ("Родился в г. Москва", [("BIRTH_PLACE", 10, 19)]),
    ("Паспорт 4509 123456", [("PASSPORT", 8, 19)]),
    ("Гражданство Российская", [("CITIZENSHIP", 12, 22)]),
    ("Паспорт выдан ОВД района", [("ISSUING_AUTHORITY", 14, 17)]),
    ("Код подразделения 770-001", [("DIVISION_CODE", 18, 25)]),
    ("Дата выдачи 20.04.2015", [("ISSUE_DATE", 12, 22)]),
    ("Водительское удостоверение 7712 345678", [("DRIVING_LICENSE", 27, 38)]),
    ("Адрес: г. Москва, ул. Ленина, д. 5", [("ADDRESS", 7, 34)]),
    ("Почта a@b.com", [("EMAIL", 6, 13)]),
    ("Телефон +7 912 345-67-89", [("PHONE", 8, 24)]),
    ("ИНН 7707083893", [("INN", 4, 14)]),
    ("Карта 4111111111111111", [("CARD", 6, 22)]),
    ("cvv 123", [("CVV", 4, 7)]),
    ("Пин 1234", [("PIN", 4, 8)]),
    ("Держатель карты Иван Петров", [("CARD_HOLDER", 16, 27)]),
    # Negative cases (no PII).
    ("Поэт Александр Пушкин написал роман.", []),
    ("Сумма операции составила 15000 рублей.", []),
    ("Отделение банка по адресу г. Москва, ул. Ленина, д. 5", []),
    ("Число 7707083893 просто", []),
]


def evaluate() -> dict:
    engine = MaskingEngine(ner_enabled=False)
    tp = fp = fn = 0
    per_type: dict[str, dict] = {}
    for text, expected in CASES:
        detected = resolve_spans(engine.detect(text))
        detected_set = {(s.type, s.start, s.end) for s in detected}
        expected_set = set(expected)
        for d in detected_set:
            if d in expected_set:
                tp += 1
                per_type.setdefault(d[0], {"tp": 0, "fp": 0, "fn": 0})["tp"] += 1
            else:
                fp += 1
                per_type.setdefault(d[0], {"tp": 0, "fp": 0, "fn": 0})["fp"] += 1
        for e in expected_set:
            if e not in detected_set:
                fn += 1
                per_type.setdefault(e[0], {"tp": 0, "fp": 0, "fn": 0})["fn"] += 1

    def f1(tp_, fp_, fn_):
        p = tp_ / (tp_ + fp_) if tp_ + fp_ else 0.0
        r = tp_ / (tp_ + fn_) if tp_ + fn_ else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        return p, r, f

    overall = f1(tp, fp, fn)
    return {
        "overall": {"precision": overall[0], "recall": overall[1], "f1": overall[2]},
        "per_type": {
            t: {"precision": f1(v["tp"], v["fp"], v["fn"])[0],
                "recall": f1(v["tp"], v["fp"], v["fn"])[1],
                "f1": f1(v["tp"], v["fp"], v["fn"])[2]}
            for t, v in per_type.items()
        },
    }


if __name__ == "__main__":
    import json

    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))