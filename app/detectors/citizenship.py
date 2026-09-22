"""Citizenship detector (PD05).

A nationality word is flagged when preceded by citizenship context
(гражданство, гражданин, гражданка).
"""

from __future__ import annotations

import re

from app.detectors.base import RegexDetector, context_before

# Nationality adjectives/nouns (Russian).
_CITIZENSHIP_RE = re.compile(
    r"(?<![А-ЯЁа-яё])\b(?:Российск\w+|РФ|граждан\w+|иностранн\w+|"
    r"Белорусск\w+|Казахстанск\w+|Украинск\w+|Армянск\w+|"
    r"Грузинск\w+|Таджикск\w+|Узбекск\w+|Киргизск\w+|Молдавск\w+)\b"
)

_CITIZENSHIP_KEYWORDS = ("гражданство", "гражданин", "гражданка", "гражданином")


class CitizenshipDetector(RegexDetector):
    type = "CITIZENSHIP"
    pattern = _CITIZENSHIP_RE
    priority = 30

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match, n_words=3)
        return any(kw in before for kw in _CITIZENSHIP_KEYWORDS)