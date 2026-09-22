"""Person name detector (PD01).

Matches capitalized name sequences (2-3 words) as a fallback to NER. A name is
only flagged in a personal context (client, applicant, document context), and
suppressed in a non-personal context (poet, author, literary mention) per F01.
"""

from __future__ import annotations

import re

from app.detectors.base import RegexDetector, context_before

_PERSONAL_KEYWORDS = (
    "клиент",
    "заявитель",
    "родился",
    "родилась",
    "проживает",
    "проживающ",
    "паспорт",
    "гражданин",
    "гражданка",
    "держатель",
    "владелец",
    "сотрудник",
    "работник",
    "подписал",
    "подготовил",
    "обратился",
    "зарегистрирован",
    "зарегистрирована",
    "рождения",
    "выдан",
    "выдано",
)

_NON_PERSONAL_KEYWORDS = (
    "поэт",
    "писатель",
    "автор",
    "произведение",
    "роман",
    "стихотворение",
    "книга",
)

# Two or three capitalized words (Russian names). The first word must not be a
# context keyword (e.g. "Клиент"), so the name is matched after the keyword.
_KEYWORD_ALT = "|".join(_PERSONAL_KEYWORDS)
_NAME_RE = re.compile(
    rf"(?<![А-ЯЁа-яё])\b(?!(?i:{_KEYWORD_ALT})\b)[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?"
    rf"(?:\s+[А-ЯЁ][а-яё]+){{1,2}}\b"
)


class PersonDetector(RegexDetector):
    type = "PERSON"
    pattern = _NAME_RE
    priority = 20

    def validate(self, text: str, match: re.Match) -> bool:
        before = context_before(text, match, n_words=6)
        if any(kw in before for kw in _NON_PERSONAL_KEYWORDS):
            return False
        # The match must not begin with a context keyword (e.g. "Клиент").
        first_word = match.group(0).split()[0].lower()
        if first_word in _PERSONAL_KEYWORDS:
            return False
        return any(kw in before for kw in _PERSONAL_KEYWORDS)