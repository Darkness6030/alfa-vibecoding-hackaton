"""Explicit citizenship fields in RU/EN, with conservative citizen context."""

import re
from app.detectors.base import RegexDetector
from app.detectors.language import SEPARATOR, words


class CitizenshipDetector(RegexDetector):
    type = "CITIZENSHIP"
    priority = 35
    pattern = re.compile(
        rf"\b(?:гражданство|citizenship|nationality){SEPARATOR}(?P<value>{words(4)})",
        re.IGNORECASE,
    )
    citizen_pattern = re.compile(
        rf"\b(?:гражданин|гражданка){SEPARATOR}(?P<value>российская\s++федерация|российск\w*+|росси[яи]|рф|беларус[ьи]|казахстан\w*+|украин\w*+|армени\w*+|грузи\w*+)\b",
        re.IGNORECASE,
    )

    def detect(self, text):
        spans = super().detect(text)
        # Reuse the standard span extraction without mutating shared detector state.
        extra = RegexDetector()
        extra.type, extra.priority, extra.pattern = (
            self.type,
            self.priority,
            self.citizen_pattern,
        )
        return spans + extra.detect(text)
