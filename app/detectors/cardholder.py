"""Card holder name detector (PD17).

A name is flagged as the card holder when preceded by card-holder context
(держатель карты, card holder, владелец карты).
"""

from __future__ import annotations

import re

from app.detectors.base import RegexDetector, context_before

# Latin or Cyrillic name (card holder names are often in Latin on cards).
_NAME_RE = re.compile(
    r"(?<![A-Za-zА-ЯЁа-яё])\b(?:[A-Z][a-z]+|[А-ЯЁ][а-яё]+)"
    r"(?:\s+(?:[A-Z][a-z]+|[А-ЯЁ][а-яё]+)){1,2}\b"
)

_CARDHOLDER_KEYWORDS = ("держатель карты", "card holder", "владелец карты", "держатель")


class CardHolderDetector(RegexDetector):
    type = "CARD_HOLDER"
    pattern = _NAME_RE
    priority = 30

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match, n_words=4)
        return any(kw in before for kw in _CARDHOLDER_KEYWORDS)