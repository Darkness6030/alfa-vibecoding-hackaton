"""Temporary email detector.

K2a: a single temporary detector used only to verify the interval/token
mechanics. Real detectors for PD01-PD17 arrive in K3/K4. This detector is not
presented as complete PII coverage.
"""

from __future__ import annotations

import re

from app.core import Span

_EMAIL_RE = re.compile(
    r"[A-Za-z0-9а-яА-ЯёЁ._%+-]+@[A-Za-z0-9а-яА-ЯёЁ.-]+\.[A-Za-zа-яА-ЯёЁ]{2,}"
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