"""Email spans with a start boundary to avoid repeated scans of long runs."""

from __future__ import annotations

import re

from app.core import Span

_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9а-яА-ЯёЁ._%+-])[A-Za-z0-9а-яА-ЯёЁ._%+-]++@[A-Za-z0-9а-яА-ЯёЁ.-]+\.[A-Za-zа-яА-ЯёЁ]{2,}"
)


class EmailDetector:
    type = "EMAIL"

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for m in _EMAIL_RE.finditer(text):
            spans.append(
                Span(start=m.start(), end=m.end(), type=self.type, value=m.group(0))
            )
        return spans
