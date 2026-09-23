"""Masking engine.

K4b: the engine runs a set of structured detectors over the input, resolves
overlapping spans by priority, replaces them with opaque typed tokens, and
returns the masked text plus the token->value mapping for exact restoration.

All PD01-PD17 categories are represented:
  PD01 PERSON, PD02 BIRTH_DATE, PD03 BIRTH_PLACE, PD04 PASSPORT,
  PD05 CITIZENSHIP, PD06 ISSUING_AUTHORITY, PD07 DIVISION_CODE,
  PD08 ISSUE_DATE, PD09 DRIVING_LICENSE, PD10 ADDRESS, PD11 EMAIL,
  PD12 PHONE, PD13 INN, PD14 CARD, PD15 CVV, PD16 PIN, PD17 CARD_HOLDER.

Natasha NER (PER/LOC) is an optional supplementary source for PD01/PD03/PD10;
it degrades gracefully when natasha is not installed.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core import Span, MaskResult, mask_resolved, resolve_spans
import re
from app.metrics import detected, masked, measured
from app.detectors.address import AddressDetector, BirthPlaceDetector
from app.detectors.card import CardNumberDetector, CvvDetector, PinDetector
from app.detectors.cardholder import CardHolderDetector
from app.detectors.citizenship import CitizenshipDetector
from app.detectors.dates import BirthDateDetector, IssueDateDetector
from app.detectors.driving import DrivingLicenseDetector
from app.detectors.email import EmailDetector
from app.detectors.inn import InnDetector
from app.detectors.issuing import IssuingAuthorityDetector
from app.detectors.ner import NerDetector
from app.detectors.passport import DivisionCodeDetector, PassportDetector
from app.detectors.person import PersonDetector
from app.detectors.phone import PhoneDetector


_DIGIT = re.compile(r"\d")
_NUMERIC_TYPES = frozenset(
    {
        "BIRTH_DATE",
        "ISSUE_DATE",
        "PASSPORT",
        "DRIVING_LICENSE",
        "DIVISION_CODE",
        "PHONE",
        "INN",
        "CARD",
        "CVV",
        "PIN",
    }
)


@dataclass(frozen=True)
class ProcessResult:
    result: str
    masked: bool


class MaskingEngine:
    """Runs detectors and produces reversible tokens."""

    def __init__(
        self,
        ner_enabled: bool = False,
        mask_types: set[str] | None = None,
        detect_types: set[str] | None = None,
        masking_enabled: bool = True,
        mask_mode: str = "token",
        combinations=(),
        custom_patterns=(),
    ) -> None:
        self._detectors = [
            NerDetector(enabled=ner_enabled),
            PersonDetector(),
            BirthDateDetector(),
            BirthPlaceDetector(),
            PassportDetector(),
            CitizenshipDetector(),
            IssuingAuthorityDetector(),
            DivisionCodeDetector(),
            IssueDateDetector(),
            DrivingLicenseDetector(),
            AddressDetector(),
            EmailDetector(),
            PhoneDetector(),
            InnDetector(),
            CardNumberDetector(),
            CvvDetector(),
            PinDetector(),
            CardHolderDetector(),
        ]
        self._mask_types = set(mask_types) if mask_types is not None else None
        self._detect_types = (
            set(detect_types) if detect_types is not None else self._mask_types
        )
        self._masking_enabled = masking_enabled
        self._mask_mode = mask_mode
        self._combinations = dict(combinations)
        self._patterns = [(t, re.compile(p, re.IGNORECASE)) for t, p in custom_patterns]

    def _enabled(self, type_: str) -> bool:
        return self._detect_types is None or type_ in self._detect_types

    def _custom_spans(self, text: str) -> list[Span]:
        spans = []
        for type_, pattern in self._patterns:
            if not self._enabled(type_):
                continue
            spans.extend(
                Span(m.start(), m.end(), type_, m.group(), 70)
                for m in pattern.finditer(text)
                if m.end() > m.start()
            )
        return spans

    def detect(self, text: str) -> list[Span]:
        spans = []
        has_digits = _DIGIT.search(text) is not None
        for detector in self._detectors:
            if not has_digits and detector.type in _NUMERIC_TYPES:
                continue
            if detector.type != "NER" and not self._enabled(detector.type):
                continue
            spans.extend(s for s in detector.detect(text) if self._enabled(s.type))
        spans.extend(self._custom_spans(text))
        return spans

    def _selected(self, span: Span, types: frozenset[str]) -> bool:
        return (
            self._masking_enabled
            and (self._mask_types is None or span.type in self._mask_types)
            and set(self._combinations.get(span.type, ())) <= types
        )

    @staticmethod
    def _redact(text: str, resolved: list[Span]) -> MaskResult:
        parts, cursor = [], 0
        for span in resolved:
            parts.extend([text[cursor : span.start], "*" * (span.end - span.start)])
            cursor = span.end
        parts.append(text[cursor:])
        return MaskResult("".join(parts), {}, bool(resolved))

    def mask(self, text: str) -> MaskResult:
        with measured("detect"):
            spans = self.detect(text)
        types = frozenset(s.type for s in spans)
        resolved = resolve_spans(s for s in spans if self._selected(s, types))
        if self._mask_mode == "redact":
            res = self._redact(text, resolved)
        else:
            with measured("mask"):
                res = mask_resolved(text, resolved)
        res.detected_types = types
        for span in spans:
            detected.labels(type=span.type).inc()
        for span in resolved:
            masked.labels(type=span.type).inc()
        return res

    def process(self, payload: str) -> ProcessResult:
        res = self.mask(payload)
        return ProcessResult(result=res.masked_text, masked=res.masked)
