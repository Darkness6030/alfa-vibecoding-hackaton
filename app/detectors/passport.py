"""Passport detectors (PD04 series/number, PD07 code of division).

Passport series/number: 4 digits + 6 digits (or 2+2 series) with passport
context. Code of division: XXX-XXX with context.
"""

from __future__ import annotations

import re

from app.detectors.base import RegexDetector, context_before

# Series (4 digits) + number (6 digits), optional space.
_PASSPORT_RE = re.compile(r"(?<!\d)\d{4}\s?\d{6}(?!\d)")
# Code of division: XXX-XXX.
_DIVISION_RE = re.compile(r"(?<!\d)\d{3}-\d{3}(?!\d)")

_PASSPORT_KEYWORDS = ("паспорт", "паспорта", "серия", "номер паспорта")
_DIVISION_KEYWORDS = ("код подразделения", "кодом подразделения", "подразделения")


class PassportDetector(RegexDetector):
    type = "PASSPORT"
    pattern = _PASSPORT_RE
    priority = 50

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match)
        return any(kw in before for kw in _PASSPORT_KEYWORDS)


class DivisionCodeDetector(RegexDetector):
    type = "DIVISION_CODE"
    pattern = _DIVISION_RE
    priority = 50

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match)
        return any(kw in before for kw in _DIVISION_KEYWORDS)