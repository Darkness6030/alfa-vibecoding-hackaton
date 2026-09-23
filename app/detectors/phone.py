"""Phone number detector (PD12).

Matches common Russian phone formats. A bare digit run is only treated as a
phone when it has phone context (prefix, separators) or an explicit phone
keyword, to avoid flagging ordinary numbers.
"""

from __future__ import annotations

import re

from app.detectors.base import RegexDetector, context_before
from app.core import Span

# +7/8 followed by 10 digits, with optional separators/spaces.
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)"
)

_PHONE_KEYWORDS = (
    "тел",
    "телефон",
    "моб",
    "мобильн",
    "звони",
    "позвони",
    "свяжись",
    "phone",
    "telephone",
    "mobile",
    "call",
)


class PhoneDetector(RegexDetector):
    type = "PHONE"
    pattern = _PHONE_RE
    priority = 30

    def detect(self, text):
        spans = super().detect(text)
        for match in _INTERNATIONAL_RE.finditer(text):
            if not any(k in context_before(text, match, 3) for k in _PHONE_KEYWORDS):
                continue
            if not any(
                s.start <= match.start() and match.end() <= s.end for s in spans
            ):
                spans.append(
                    Span(
                        match.start(),
                        match.end(),
                        self.type,
                        match.group(),
                        self.priority,
                    )
                )
        return spans

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match)
        return match.group().startswith("+7") or any(
            kw in before for kw in _PHONE_KEYWORDS
        )


_INTERNATIONAL_RE = re.compile(r"(?<![\w+])\+(?a:(?:\d[ ()-]{0,3}){7,14}\d)(?!\d)")
