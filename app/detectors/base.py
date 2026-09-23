"""Base classes for structured detectors.

A ``RegexDetector`` matches a pattern and optionally validates each match with
context (surrounding words) before emitting a Span. Detectors are declarative:
subclass, set ``type``/``pattern``/``priority``, and override ``validate`` when
context is required.
"""

from __future__ import annotations

import re

from app.core import Span


class RegexDetector:
    type: str = "UNKNOWN"
    pattern: re.Pattern[str] | None = None
    priority: int = 0

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        if self.pattern is None:
            return spans
        for m in self.pattern.finditer(text):
            if not self.validate(text, m):
                continue
            spans.append(
                Span(
                    start=m.start("value") if "value" in m.re.groupindex else m.start(),
                    end=m.end("value") if "value" in m.re.groupindex else m.end(),
                    type=self.type,
                    value=m.group("value")
                    if "value" in m.re.groupindex
                    else m.group(0),
                    priority=self.priority,
                )
            )
        return spans

    def validate(self, _text: str, _match: re.Match) -> bool:
        """Return True when the match is PII in context. Override as needed."""
        return True


def context_before(text: str, match: re.Match, n_words: int = 2) -> str:
    """Return context before a regex match using its original text offset."""
    return context_before_offset(text, match.start(), n_words)


def context_before_offset(text: str, start: int, n_words: int = 2) -> str:
    """Return the last ``n_words`` words immediately before the match (lowercased).

    A small word window prevents a keyword from an unrelated nearby clause
    (e.g. "пин" in "пин 1234, паспорт 4509") from leaking into the context.
    """
    before = text[max(0, start - 256) : start].rstrip()
    words = before.split()
    return " ".join(words[-n_words:]).lower()


def context_after(text: str, match: re.Match, n_words: int = 3) -> str:
    """Return the first ``n_words`` words immediately after the match (lowercased)."""
    after = text[match.end() : match.end() + 256].lstrip()
    words = after.split()
    return " ".join(words[:n_words]).lower()
