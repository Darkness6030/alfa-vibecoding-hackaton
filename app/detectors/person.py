"""Context-anchored Russian names, case independent; no global famous-name bypass."""

import re
from app.detectors.base import RegexDetector
from app.core import Span
from app.detectors.language import VALUE_WORD, SEPARATOR, HORIZONTAL

_WORD = VALUE_WORD
_INITIAL = r"[^\W\d_]\."
_INITIALS = rf"{_INITIAL}(?:{HORIZONTAL}*{_INITIAL})?"
NAME = rf"(?:{_WORD}{HORIZONTAL}++{_INITIALS}|{_INITIALS}{HORIZONTAL}++{_WORD}|{_WORD}(?:{HORIZONTAL}++{_WORD}){{1,3}})"

_SINGLE_NAME = re.compile(
    rf"\b(?:first\s++name|given\s++name|middle\s++name|last\s++name|surname|имя|фамилия|отчество)"
    rf"\s*+[:—]\s*+(?P<value>{NAME}|{_WORD})", re.IGNORECASE,
)


class PersonDetector(RegexDetector):
    type = "PERSON"
    priority = 20
    pattern = re.compile(
        rf"\b(?:клиент(?:ка)?|заявитель(?:ница)?|фио|ф\.и\.о\.|сотрудник|работник|гражданин|гражданка|customer|client|full name|name|employee|applicant){SEPARATOR}(?P<value>{NAME})",
        re.IGNORECASE,
    )

    def detect(self, text):
        spans = super().detect(text)
        spans.extend(
            Span(m.start("value"), m.end("value"), self.type, m.group("value"), self.priority)
            for m in _SINGLE_NAME.finditer(text)
        )
        # QA explicitly includes a payload consisting only of a full name.
        # A patronymic signal avoids treating arbitrary three-word prose as a name.
        if not spans and len(text) <= 200:
            match = re.fullmatch(
                rf"\s*(?P<value>{_WORD}(?:{HORIZONTAL}+{_WORD}){{2}})\s*[.!?]?\s*",
                text,
                re.IGNORECASE,
            )
            if match and any(
                re.fullmatch(
                    r"[а-яё-]+(?:ович|евич|овна|евна|ична|инична)", word, re.IGNORECASE
                )
                for word in match.group("value").split()
            ):
                spans.append(
                    Span(
                        match.start("value"),
                        match.end("value"),
                        self.type,
                        match.group("value"),
                        self.priority,
                    )
                )
        return spans
