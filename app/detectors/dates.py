"""Context dates: day/year first, textual months, preserving original spelling."""

import re
from app.detectors.base import RegexDetector, context_before

_MONTH = r"(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря|january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sept|sep|october|oct|november|nov|december|dec)"
_DATE_RE = re.compile(
    rf"(?<!\d)(?=[\dA-Za-z])(?:\d{{4}}[./-]\d{{1,2}}[./-]\d{{1,2}}|\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{2,4}}|\d{{1,2}}\s++{_MONTH}\.?\s++\d{{4}}|{_MONTH}\.?\s++\d{{1,2}}(?:st|nd|rd|th)?[,]?\s++\d{{4}})(?!\d)",
    re.IGNORECASE,
)


class BirthDateDetector(RegexDetector):
    type = "BIRTH_DATE"
    pattern = _DATE_RE
    priority = 40

    def validate(self, text, match):
        before = context_before(text, match, 3)
        return any(
            k in before
            for k in (
                "дата рождения",
                "родился",
                "родилась",
                "рождения",
                "род.",
                "date of birth",
                "dob",
                "born",
            )
        )


class IssueDateDetector(RegexDetector):
    type = "ISSUE_DATE"
    pattern = _DATE_RE
    priority = 40

    def validate(self, text, match):
        before = context_before(text, match, 3)
        return any(
            k in before
            for k in (
                "дата выдачи",
                "выдан",
                "выдачи",
                "issue date",
                "date of issue",
                "issued",
            )
        )
