"""Names on a card may be uppercase and Latin or Cyrillic."""

import re
from app.detectors.base import RegexDetector
from app.detectors.language import SEPARATOR
from app.detectors.person import NAME


class CardHolderDetector(RegexDetector):
    type = "CARD_HOLDER"
    priority = 30
    pattern = re.compile(
        rf"\b(?:имя\s++держателя(?:\s++карты)?|держатель(?:\s++карты)?|владелец\s++карты|card\s*+holder(?:\s++name)?){SEPARATOR}(?P<value>{NAME})",
        re.IGNORECASE,
    )
