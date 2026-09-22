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

from app.core import Span, mask, resolve_spans, restore
from app.metrics import detected, masked
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


@dataclass(frozen=True)
class ProcessResult:
    result: str
    masked: bool


class MaskingEngine:
    """Runs detectors and produces reversible tokens."""

    def __init__(self, ner_enabled: bool = True, mask_types: set[str] | None = None) -> None:
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

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for detector in self._detectors:
            if self._mask_types is not None and detector.type not in self._mask_types:
                continue
            spans.extend(detector.detect(text))
        return spans

    def mask(self, text: str):
        spans = self.detect(text)
        res = mask(text, spans)
        for span in spans:
            detected.labels(type=span.type).inc()
        for span in resolve_spans(spans):
            masked.labels(type=span.type).inc()
        return res

    def process(self, payload: str) -> ProcessResult:
        res = self.mask(payload)
        return ProcessResult(result=res.masked_text, masked=res.masked)