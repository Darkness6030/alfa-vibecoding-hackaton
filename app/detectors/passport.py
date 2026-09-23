"""Russian document formats, with Russian or English field labels."""

import re
from app.core import Span
from app.detectors.base import RegexDetector, context_before
from app.detectors.language import SEPARATOR

_FIRST_DIGIT = re.compile(r"\d")
_SERIES = r"(?:\d{4}|\d{2}[ \t]++\d{2})"
_PASSPORT_RE = re.compile(
    rf"(?<!\d)(?P<series>{_SERIES})(?P<separator>\s*+(?:(?:номер|number|no\.?|№)\s*+)?)(?P<number>\d{{6}})(?!\d)",
    re.IGNORECASE,
)
_PART_RE = re.compile(
    rf"(?<!\w)(?:(?:серия|series){SEPARATOR}(?P<series>{_SERIES})|"
    rf"(?:номер|number|no\.?|№)(?:\s++(?:паспорта|passport))?{SEPARATOR}(?P<number>\d{{6}}))(?!\d)",
    re.IGNORECASE,
)
_DRIVING_CONTEXT = re.compile(
    r"водительск|\b(?:ву|в/у|в\.у\.|права|driving|driver[’']?s?)\b", re.I
)
_NONPERSONAL = re.compile(r"издели|товар|продукт|\bproduct\b", re.I)


def driving_context(before: str) -> bool:
    return bool(_DRIVING_CONTEXT.search(before))


class DocumentNumberDetector(RegexDetector):
    """Full documents and explicitly labelled independent parts are separate rules."""

    pattern = _PASSPORT_RE

    def detect(self, text):
        spans = []
        for match in self.pattern.finditer(text):
            if not self.validate(text, match):
                continue
            groups = ("series", "number") if match.group("separator").strip() else (0,)
            for group in groups:
                spans.append(
                    Span(
                        match.start(group),
                        match.end(group),
                        self.type,
                        match.group(group),
                        self.priority,
                    )
                )
        for match in _PART_RE.finditer(text):
            group = "series" if match.group("series") is not None else "number"
            # Validate at the value, so both "номер паспорта" and "passport number" work.
            value_match = _FIRST_DIGIT.search(text, match.start(group))
            if not self.validate(text, value_match):
                continue
            start, end = match.span(group)
            if not any(s.start <= start and end <= s.end for s in spans):
                spans.append(
                    Span(start, end, self.type, text[start:end], self.priority)
                )
        return spans


class PassportDetector(DocumentNumberDetector):
    type = "PASSPORT"
    priority = 50

    def validate(self, text, match):
        before = context_before(text, match, n_words=6)
        if driving_context(before) or _NONPERSONAL.search(before):
            return False
        return bool(re.search(r"паспорт|\bpassport\b", before))


class DivisionCodeDetector(RegexDetector):
    type = "DIVISION_CODE"
    pattern = re.compile(r"(?<!\d)\d{3}-\d{3}(?!\d)")
    priority = 50

    def validate(self, text, match):
        before = context_before(text, match, 3)
        return any(
            k in before for k in ("подразделения", "department code", "division code")
        )
