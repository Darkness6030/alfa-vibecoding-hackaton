"""Issuing authorities: scan once to punctuation or the next structured field."""

import re
from app.core import Span
from app.detectors.base import RegexDetector
from app.detectors.language import SEPARATOR

_AUTHORITY_START = re.compile(
    rf"\b(?:выдан[ао]?|орган(?:,?\s++выдавший\s++паспорт)?|кем\s++выдан|issued\s++by|issuing\s++authority){SEPARATOR}"
    r"(?P<value>(?:овд|уфмс|мвд|гувд|увд|фмс|отдел\w*+|управлени\w*+|ministry|department|office|authority|hmpo|hm\s++passport\s++office)\b)",
    re.IGNORECASE,
)
_AUTHORITY_END = re.compile(
    r"[,;\n\d]|\b(?:код\s++подразделения|дата\s++выдачи|паспорт|выдан[ао]?|кем\s++выдан|"
    r"department\s++code|division\s++code|issue\s++date|date\s++of\s++issue|passport|issued\s++by|"
    r"issuing\s++authority|phone|email|телефон|почта)\b",
    re.IGNORECASE,
)


class IssuingAuthorityDetector(RegexDetector):
    type = "ISSUING_AUTHORITY"
    priority = 45
    pattern = _AUTHORITY_START

    def detect(self, text):
        spans = []
        for match in self.pattern.finditer(text):
            boundary = _AUTHORITY_END.search(text, match.end())
            end = boundary.start() if boundary else len(text)
            value = text[match.start("value") : end].rstrip(" .\t")
            spans.append(
                Span(
                    match.start("value"),
                    match.start("value") + len(value),
                    self.type,
                    value,
                    self.priority,
                )
            )
        return spans
