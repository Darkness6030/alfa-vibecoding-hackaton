"""INN detector (PD13).

A 10- or 12-digit number is an INN only when preceded by the INN keyword, to
avoid flagging arbitrary numbers.
"""

from __future__ import annotations

import re

from app.detectors.base import RegexDetector, context_before

_INN_RE = re.compile(r"(?<!\d)\d{10}(?!\d)|(?<!\d)\d{12}(?!\d)")

_INN_KEYWORDS = ("инн", "иин", "и.н.н")


class InnDetector(RegexDetector):
    type = "INN"
    pattern = _INN_RE
    priority = 40

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match)
        return any(kw in before for kw in _INN_KEYWORDS)