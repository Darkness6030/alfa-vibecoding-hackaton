"""Date detectors (PD02 date of birth, PD08 date of issue).

A date is only flagged when it appears with the relevant context keyword, so a
birth date is distinguished from an issue date and from arbitrary dates.
"""

from __future__ import annotations

import re

from app.detectors.base import RegexDetector, context_before

# DD.MM.YYYY or DD.MM.YY, also DD/MM/YYYY.
_DATE_RE = re.compile(r"(?<!\d)\d{1,2}[./]\d{1,2}[./]\d{2,4}(?!\d)")

_BIRTH_KEYWORDS = ("дата рождения", "родился", "родилась", "рождения", "род.")
_ISSUE_KEYWORDS = ("дата выдачи", "выдан", "выдана", "выдачи")


class BirthDateDetector(RegexDetector):
    type = "BIRTH_DATE"
    pattern = _DATE_RE
    priority = 40

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match)
        return any(kw in before for kw in _BIRTH_KEYWORDS)


class IssueDateDetector(RegexDetector):
    type = "ISSUE_DATE"
    pattern = _DATE_RE
    priority = 40

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match)
        return any(kw in before for kw in _ISSUE_KEYWORDS)