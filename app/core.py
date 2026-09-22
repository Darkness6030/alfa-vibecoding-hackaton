"""Interval/token core with exact restoration.

K2a: represents detected PII spans as half-open [start, end) character
intervals, replaces them with opaque typed tokens, and restores the original
string exactly.

Design (docs/decisions.md D04):
- Tokens are opaque: they do not contain the original value and cannot be
  reversed without the protected mapping.
- Tokens are typed so the role of the value is preserved for an LLM.
- Tokens are fixed-length so no token is a substring of another, which makes
  exact restoration safe.
- Token generation guarantees no collision with the original text.
- Overlap resolution is deterministic: earliest start wins, longest span wins
  on a tie.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Iterable

# Fixed-length random part so all tokens have identical length and no token is
# a substring of another. 16 hex chars = 64 bits of entropy per token.
_TOKEN_HEX_LEN = 16
_TOKEN_PREFIX = "{{"
_TOKEN_SUFFIX = "}}"


@dataclass(frozen=True)
class Span:
    """A detected PII interval in the original text.

    ``start``/``end`` are half-open character offsets into the original string.
    ``value`` is the exact original substring (used for restoration).
    ``priority`` resolves intersections: higher priority wins on overlap.
    """

    start: int
    end: int
    type: str
    value: str
    priority: int = 0

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"invalid span [{self.start}, {self.end})")
        if len(self.value) != self.end - self.start:
            raise ValueError("span value length does not match interval")


def _make_token(type_: str, hex_part: str) -> str:
    return f"{_TOKEN_PREFIX}{type_}:{hex_part}{_TOKEN_SUFFIX}"


def _random_hex() -> str:
    return secrets.token_hex(_TOKEN_HEX_LEN // 2)


def _token_collides(token: str, text: str) -> bool:
    return token in text


def _generate_token(type_: str, text: str) -> str:
    """Generate an opaque token that does not collide with ``text``."""
    while True:
        token = _make_token(type_, _random_hex())
        if not _token_collides(token, text):
            return token


def resolve_spans(spans: Iterable[Span]) -> list[Span]:
    """Resolve overlapping spans deterministically.

    Sort by (-priority, start, -end): higher priority wins on overlap; on equal
    priority the earliest start wins and, on a tie, the longest span wins. A
    span is dropped if it overlaps ANY already-accepted span (checked against
    all accepted spans, since priority ordering can place a later-starting
    high-priority span before an earlier-starting lower-priority one).
    """
    ordered = sorted(spans, key=lambda s: (-s.priority, s.start, -s.end))
    accepted: list[Span] = []
    for span in ordered:
        if any(span.start < a.end and a.start < span.end for a in accepted):
            continue
        accepted.append(span)
    return accepted


@dataclass
class MaskResult:
    """Result of masking a text.

    ``masked_text`` is the text with spans replaced by tokens.
    ``mapping`` maps each token to its original value (for restoration).
    ``masked`` is True when at least one span was replaced.
    """

    masked_text: str
    mapping: dict[str, str] = field(default_factory=dict)
    masked: bool = False


def mask(text: str, spans: Iterable[Span]) -> MaskResult:
    """Replace resolved spans with opaque typed tokens.

    Builds the masked text by walking the original string and substituting each
    accepted span with a fresh token. The mapping token -> original value is
    returned for exact restoration.
    """
    resolved = resolve_spans(spans)
    # Build the masked text in start order (resolve_spans returns priority order).
    ordered = sorted(resolved, key=lambda s: s.start)
    mapping: dict[str, str] = {}
    parts: list[str] = []
    cursor = 0
    for span in ordered:
        if span.end > len(text):
            raise ValueError(f"span [{span.start}, {span.end}) exceeds text length")
        if span.start > cursor:
            parts.append(text[cursor : span.start])
        token = _generate_token(span.type, text)
        mapping[token] = span.value
        parts.append(token)
        cursor = span.end
    if cursor < len(text):
        parts.append(text[cursor:])
    masked_text = "".join(parts)
    return MaskResult(masked_text=masked_text, mapping=mapping, masked=bool(mapping))


def restore(masked_text: str, mapping: dict[str, str]) -> str:
    """Restore the original text exactly by replacing tokens with values.

    Tokens are fixed-length and unique, so a single-pass scan is exact and no
    token is a substring of another.
    """
    if not mapping:
        return masked_text
    # Sort tokens by length descending so longer tokens are matched first; all
    # tokens are equal length here, but this keeps the scan robust.
    tokens = sorted(mapping, key=len, reverse=True)
    result = masked_text
    for token in tokens:
        result = result.replace(token, mapping[token])
    return result