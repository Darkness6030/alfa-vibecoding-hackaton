"""Driving license detector (PD09).

Series/number of a driving license is flagged when preceded by driving-license
context (водительское, ВУ, удостоверение).
"""

from __future__ import annotations

import re

from app.detectors.base import RegexDetector, context_before

# Driving license: 4 digits + 6 digits, or 2+2 series + 6 digits.
_DRIVING_RE = re.compile(r"(?<!\d)\d{4}\s?\d{6}(?!\d)")

_DRIVING_KEYWORDS = ("водительск", "в.у.", "в у", "удостоверение", "права")


class DrivingLicenseDetector(RegexDetector):
    type = "DRIVING_LICENSE"
    pattern = _DRIVING_RE
    priority = 50

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match, n_words=3)
        return any(kw in before for kw in _DRIVING_KEYWORDS)