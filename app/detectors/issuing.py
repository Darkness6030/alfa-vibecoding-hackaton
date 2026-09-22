"""Issuing authority detector (PD06).

The authority that issued a document is flagged when preceded by issue context
(выдан, выдано, орган, кем выдан).
"""

from __future__ import annotations

import re

from app.detectors.base import RegexDetector, context_before

# Issuing authority: capitalized phrase after issue context, e.g.
# "выдан ОВД района" or "выдан УФМС России".
_AUTHORITY_RE = re.compile(
    r"(?<![А-ЯЁа-яё])\b(?:ОВД\w*|УФМС\w*|МВД\w*|ГУВД\w*|"
    r"УВД\w*|ФМС\w*|отдел\w*\s+[А-ЯЁ][а-яё-]+|"
    r"управление\w*\s+[А-ЯЁ][а-яё-]+)\b"
)

_AUTHORITY_KEYWORDS = ("выдан", "выдано", "выдана", "орган", "кем выдан", "выдавший")


class IssuingAuthorityDetector(RegexDetector):
    type = "ISSUING_AUTHORITY"
    pattern = _AUTHORITY_RE
    priority = 30

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match, n_words=4)
        return any(kw in before for kw in _AUTHORITY_KEYWORDS)