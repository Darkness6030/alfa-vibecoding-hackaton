"""Phone number detector (PD12).

Matches common Russian phone formats. A bare digit run is only treated as a
phone when it has phone context (prefix, separators) or an explicit phone
keyword, to avoid flagging ordinary numbers.
"""

from __future__ import annotations

import re

from app.detectors.base import RegexDetector, context_before

# +7/8 followed by 10 digits, with optional separators/spaces.
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)"
)

_PHONE_KEYWORDS = ("тел", "телефон", "моб", "мобильн", "звони", "позвони", "свяжись")


class PhoneDetector(RegexDetector):
    type = "PHONE"
    pattern = _PHONE_RE
    priority = 30

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match)
        return any(kw in before for kw in _PHONE_KEYWORDS)