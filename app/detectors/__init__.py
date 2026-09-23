"""Detector API.

A detector identifies PII spans in a text and returns them as ``Span`` objects
with half-open character offsets. Detectors are composable and added without
changing the core (docs/reports/history/decisions.md D04, requirements F02).
"""

from __future__ import annotations

from typing import Protocol

from app.core import Span


class Detector(Protocol):
    """Interface every detector implements."""

    type: str

    def detect(self, text: str) -> list[Span]:
        """Return detected PII spans in ``text``."""
        ...
