"""K2a tests: interval/token core, exact restoration, detector API.

These verify the mechanics of masking/restoration, not PII coverage (only the
temporary email detector is wired in).
"""

from __future__ import annotations

import pytest

from app.core import Span, mask, resolve_spans, restore
from app.engine import MaskingEngine


def test_mask_replaces_email_with_token():
    res = mask("contact me at a@b.com please", [Span(14, 21, "EMAIL", "a@b.com")])
    assert res.masked is True
    assert "a@b.com" not in res.masked_text
    assert "{{EMAIL:" in res.masked_text
    assert res.masked_text.endswith(" please")


def test_restore_round_trip_exact():
    original = "contact me at a@b.com please"
    res = mask(original, [Span(14, 21, "EMAIL", "a@b.com")])
    assert restore(res.masked_text, res.mapping) == original


def test_restore_round_trip_unicode_and_emoji():
    original = "Почта: иван@пример.рф и смайлик 😀 и ещё a@b.com"
    engine = MaskingEngine()
    res = engine.mask(original)
    assert restore(res.masked_text, res.mapping) == original


def test_restore_preserves_whitespace_and_newlines():
    original = "line1 a@b.com\nline2  b@c.com\tend"
    engine = MaskingEngine()
    res = engine.mask(original)
    assert restore(res.masked_text, res.mapping) == original


def test_repeated_value_maps_to_distinct_tokens():
    original = "a@b.com and again a@b.com"
    engine = MaskingEngine()
    res = engine.mask(original)
    # Two occurrences -> two distinct tokens (no global stable identifier).
    assert len(res.mapping) == 2
    assert restore(res.masked_text, res.mapping) == original


def test_token_does_not_collide_with_original_text():
    # A token must never appear in the original text.
    original = "a@b.com"
    res = mask(original, [Span(0, 7, "EMAIL", "a@b.com")])
    assert res.masked_text not in original
    assert restore(res.masked_text, res.mapping) == original


def test_no_pii_returns_unchanged_and_not_masked():
    original = "просто текст без персональных данных"
    engine = MaskingEngine()
    res = engine.mask(original)
    assert res.masked is False
    assert res.masked_text == original
    assert res.mapping == {}


def test_overlap_resolution_earliest_start_wins():
    # Two overlapping spans: [0,5) and [3,8). Earliest start wins.
    spans = [
        Span(3, 8, "B", "34567"),
        Span(0, 5, "A", "01234"),
    ]
    resolved = resolve_spans(spans)
    assert len(resolved) == 1
    assert resolved[0].start == 0
    assert resolved[0].end == 5


def test_overlap_resolution_longest_wins_on_tie():
    spans = [
        Span(0, 5, "A", "01234"),
        Span(0, 8, "B", "01234567"),
    ]
    resolved = resolve_spans(spans)
    assert len(resolved) == 1
    assert resolved[0].end == 8


def test_adjacent_spans_both_kept():
    spans = [
        Span(0, 3, "A", "abc"),
        Span(3, 6, "B", "def"),
    ]
    resolved = resolve_spans(spans)
    assert len(resolved) == 2


def test_span_validation():
    with pytest.raises(ValueError):
        Span(5, 2, "A", "x")
    with pytest.raises(ValueError):
        Span(0, 3, "A", "toolong")


def test_mask_rejects_out_of_bounds_span():
    with pytest.raises(ValueError):
        mask("short", [Span(0, 10, "A", "shorttext")])


def test_engine_detects_email():
    engine = MaskingEngine()
    spans = engine.detect("mail a@b.com here")
    assert len(spans) == 1
    assert spans[0].type == "EMAIL"
    assert spans[0].value == "a@b.com"


def test_engine_process_marks_masked():
    engine = MaskingEngine()
    res = engine.process("mail a@b.com here")
    assert res.masked is True
    assert "a@b.com" not in res.result