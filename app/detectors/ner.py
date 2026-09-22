"""Natasha NER detector (candidate generator for PD01/PD03/PD10).

Runs the natasha NER pipeline (PER/LOC) as a supplementary candidate source.
Natasha is an optional dependency: if it is not installed, the detector returns
no spans (graceful degradation) instead of crashing.

Context: a PER/LOC span is only emitted when it appears in a personal context
(personal keywords nearby), so a famous name in a literary context is not
flagged as PII (requirements F01).
"""

from __future__ import annotations

import re

from app.core import Span
from app.detectors.base import context_before

# Personal context keywords: presence indicates a personal-data mention.
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
    "адрес",
    "рождения",
    "выдан",
    "выдано",
)

# Non-personal context: presence suppresses the span (famous/literary mention).
_NON_PERSONAL_KEYWORDS = (
    "поэт",
    "писатель",
    "автор",
    "произведение",
    "роман",
    "стихотворение",
    "книга",
    "улица",
    "проспект",
    "площадь",
    "станция",
    "аэропорт",
    "вокзал",
)


class _NatashaPipeline:
    """Lazily-loaded singleton natasha pipeline."""

    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            from natasha import Doc, NewsEmbedding, NewsMorphTagger, NewsNERTagger, Segmenter

            segmenter = Segmenter()
            emb = NewsEmbedding()
            cls._instance = (
                segmenter,
                emb,
                NewsMorphTagger(emb),
                NewsNERTagger(emb),
                Doc,
            )
        return cls._instance


class NerDetector:
    type = "NER"
    priority = 20

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled

    def detect(self, text: str) -> list[Span]:
        if not self._enabled:
            return []
        try:
            segmenter, emb, morph_tagger, ner_tagger, Doc = _NatashaPipeline.get()
        except ImportError:
            return []

        doc = Doc(text)
        doc.segment(segmenter)
        doc.tag_morph(morph_tagger)
        doc.tag_ner(ner_tagger)

        spans: list[Span] = []
        for span in doc.spans:
            if span.type not in ("PER", "LOC"):
                continue
            if not self._is_personal(text, span.start, span.stop):
                continue
            pii_type = "PERSON" if span.type == "PER" else "LOCATION"
            spans.append(
                Span(
                    start=span.start,
                    end=span.stop,
                    type=pii_type,
                    value=text[span.start : span.stop],
                    priority=self.priority,
                )
            )
        return spans

    def _is_personal(self, text: str, start: int, end: int) -> bool:
        before = context_before(text, _FakeMatch(start), n_words=6)
        if any(kw in before for kw in _NON_PERSONAL_KEYWORDS):
            return False
        return any(kw in before for kw in _PERSONAL_KEYWORDS)


class _FakeMatch:
    """Minimal match-like object for context_before."""

    def __init__(self, start: int) -> None:
        self._start = start

    def start(self) -> int:
        return self._start