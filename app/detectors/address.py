"""Address (PD10) and birth place (PD03) detectors.

An address is flagged when preceded by address context (адрес, проживает,
зарегистрирован). A birth place is flagged when preceded by birth context
(родился в, место рождения).
"""

from __future__ import annotations

import re

from app.detectors.base import RegexDetector, context_before

# Address: city/street/house pattern, e.g. "г. Москва, ул. Ленина, д. 5".
_ADDRESS_RE = re.compile(
    r"(?:г\.?\s*[А-ЯЁ][а-яё-]+|ул\.?\s*[А-ЯЁ][а-яё-]+|"
    r"пр-т\.?\s*[А-ЯЁ][а-яё-]+|д\.?\s*\d+)(?:\s*,\s*(?:ул\.?\s*[А-ЯЁ][а-яё-]+|д\.?\s*\d+|кв\.?\s*\d+))*"
)

_ADDRESS_KEYWORDS = ("адрес", "проживает", "проживающ", "зарегистрирован", "зарегистрирована", "место жительства")
_BIRTH_PLACE_KEYWORDS = ("родился в", "родилась в", "место рождения", "родился", "родилась")
# Non-personal context: a bank branch address is not personal data (F01).
_NON_PERSONAL_KEYWORDS = ("отделение банка", "отделение", "банк", "филиал банка", "офис банка")


class AddressDetector(RegexDetector):
    type = "ADDRESS"
    pattern = _ADDRESS_RE
    priority = 30

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match, n_words=6)
        if any(kw in before for kw in _NON_PERSONAL_KEYWORDS):
            return False
        return any(kw in before for kw in _ADDRESS_KEYWORDS)


class BirthPlaceDetector(RegexDetector):
    type = "BIRTH_PLACE"
    pattern = _ADDRESS_RE
    priority = 30

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match, n_words=4)
        return any(kw in before for kw in _BIRTH_PLACE_KEYWORDS)