"""Interval/token core with exact restoration.

K2a: represents detected PII spans as half-open [start, end) character
intervals, replaces them with opaque typed tokens, and restores the original
string exactly.

Design (docs/reports/history/decisions.md D04):
- Tokens are opaque: they do not contain the original value and cannot be
  reversed without the protected mapping.
- Tokens are typed so the role of the value is preserved for an LLM.
- Tokens have explicit delimiters; restoration scans whole tokens once.
- Token generation guarantees no collision with the original text.
- Overlap resolution is deterministic: priority, then position and length.
"""

from __future__ import annotations

import secrets
import re
from bisect import bisect_left
from dataclasses import dataclass, field
from collections.abc import Iterable

# New tokens use 32 hex characters (128 random bits). The reader also accepts
# legacy token lengths so expired/foreign tokens are handled explicitly.
_TOKEN_HEX_LEN = 32
TOKEN_RE = re.compile(r"\{\{[A-Z_]+:[0-9a-f]{16,32}\}\}")
_OPEN_DELIMITER = "{{"
_CLOSE_DELIMITER = "}}"


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
        if not re.fullmatch(r"[A-Z_]{1,40}", self.type):
            raise ValueError("invalid span type")
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"invalid span [{self.start}, {self.end})")
        if len(self.value) != self.end - self.start:
            raise ValueError("span value length does not match interval")


def _make_token(type_: str, hex_part: str) -> str:
    return f"{_OPEN_DELIMITER}{type_}:{hex_part}{_CLOSE_DELIMITER}"


def _random_hex() -> str:
    return secrets.token_hex(_TOKEN_HEX_LEN // 2)


def _generate_token(type_: str, occupied: set[str]) -> str:
    """Avoid original and newly generated tokens using one request-local set."""
    while True:
        token = _make_token(type_, _random_hex())
        if token not in occupied:
            occupied.add(token)
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
    starts: list[int] = []
    for span in ordered:
        index = bisect_left(starts, span.start)
        if index and accepted[index - 1].end > span.start:
            continue
        if index < len(accepted) and accepted[index].start < span.end:
            continue
        starts.insert(index, span.start)
        accepted.insert(index, span)
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
    detected_types: frozenset[str] = frozenset()


def mask(text: str, spans: Iterable[Span]) -> MaskResult:
    """Replace resolved spans with opaque typed tokens.

    Builds the masked text by walking the original string and substituting each
    accepted span with a fresh token. The mapping token -> original value is
    returned for exact restoration.
    """
    return mask_resolved(text, resolve_spans(spans))


def mask_resolved(text: str, ordered: list[Span]) -> MaskResult:
    """Replace nonoverlapping source-order spans, already resolved by the caller."""
    mapping: dict[str, str] = {}
    occupied = {m.group() for m in TOKEN_RE.finditer(text)}
    parts: list[str] = []
    cursor = 0
    for span in ordered:
        if span.start < cursor:
            raise ValueError("spans overlap or are out of order")
        if span.end > len(text):
            raise ValueError(f"span [{span.start}, {span.end}) exceeds text length")
        if span.start > cursor:
            parts.append(text[cursor : span.start])
        if text[span.start : span.end] != span.value:
            raise ValueError("span does not match source")
        token = _generate_token(span.type, occupied)
        mapping[token] = span.value
        parts.append(token)
        cursor = span.end
    if cursor < len(text):
        parts.append(text[cursor:])
    masked_text = "".join(parts)
    return MaskResult(
        masked_text=masked_text,
        mapping=mapping,
        masked=bool(mapping),
        detected_types=frozenset(s.type for s in ordered),
    )


def restore(masked_text: str, mapping: dict[str, str]) -> str:
    """Restore the original text exactly by replacing tokens with values.

    Match whole delimited tokens in one pass; never recursively replace values.
    """
    if not mapping:
        return masked_text
    # One pass prevents cascading replacement when an original contains a token.
    return TOKEN_RE.sub(
        lambda match: mapping.get(match.group(0), match.group(0)), masked_text
    )
