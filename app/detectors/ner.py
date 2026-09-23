"""Natasha NER detector (candidate generator for PD01/PD03/PD10).

Runs the natasha NER pipeline (PER/LOC) as a supplementary candidate source.
Natasha is an optional dependency: if it is not installed, the detector returns
no spans (graceful degradation) instead of crashing.

Context: a PER/LOC span is only emitted when it appears in a personal context
(personal keywords nearby), so a famous name in a literary context is not
flagged as PII (requirements F01).
"""

from __future__ import annotations


from app.core import Span
from app.detectors.base import context_before_offset

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
            from natasha import (
                Doc,
                NewsEmbedding,
                NewsMorphTagger,
                NewsNERTagger,
                Segmenter,
            )

            segmenter = Segmenter()
            emb = NewsEmbedding()
            cls._instance = (
                segmenter,
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
            segmenter, morph_tagger, ner_tagger, doc_factory = _NatashaPipeline.get()
        except ImportError:
            return []

        doc = doc_factory(text)
        doc.segment(segmenter)
        doc.tag_morph(morph_tagger)
        doc.tag_ner(ner_tagger)

        spans: list[Span] = []
        for span in doc.spans:
            if span.type not in ("PER", "LOC"):
                continue
            if not self._is_personal(text, span.start):
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

    @staticmethod
    def _is_personal(text: str, start: int) -> bool:
        before = context_before_offset(text, start, n_words=6)
        if any(kw in before for kw in _NON_PERSONAL_KEYWORDS):
            return False
        return any(kw in before for kw in _PERSONAL_KEYWORDS)
