"""Payment card detectors (PD14 card number, PD15 CVV, PD16 PIN).

Card number: 13-19 digits, optionally grouped, validated by the Luhn checksum
or accepted when preceded by card context. CVV/PIN are only flagged when they
appear near card context to avoid flagging ordinary short numbers.
"""

from __future__ import annotations

import re

from app.detectors.base import RegexDetector, context_before

# Card number: 13-19 digits, optionally grouped in 4s. The trailing \d{0,3}
# covers the 16-digit case (4 groups of 4 with no remainder).
_CARD_RE = re.compile(
    r"(?<!\d)(?:\d{4}[\s-]?){3,4}\d{0,3}(?!\d)"
)

# CVV: 3 digits. PIN: 4 digits.
_CVV_RE = re.compile(r"(?<!\d)\d{3}(?!\d)")
_PIN_RE = re.compile(r"(?<!\d)\d{4}(?!\d)")

_CARD_KEYWORDS = ("карт", "карта", "карту", "картой", "счёт", "счет", "банк")
_CVV_KEYWORDS = ("cvv", "cvc", "код карты", "код с обратной")
_PIN_KEYWORDS = ("пин", "pin", "пароль")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class CardNumberDetector(RegexDetector):
    type = "CARD"
    pattern = _CARD_RE
    priority = 50

    def validate(self, text: str, match: re.Match) -> bool:
        digits = re.sub(r"\D", "", match.group(0))
        if not (13 <= len(digits) <= 19):
            return False
        if _luhn_ok(digits):
            return True
        before = context_before(text, match)
        return any(kw in before for kw in _CARD_KEYWORDS)


class CvvDetector(RegexDetector):
    type = "CVV"
    pattern = _CVV_RE
    priority = 60

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match)
        return any(kw in before for kw in _CVV_KEYWORDS)


class PinDetector(RegexDetector):
    type = "PIN"
    pattern = _PIN_RE
    priority = 60

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match)
        return any(kw in before for kw in _PIN_KEYWORDS)