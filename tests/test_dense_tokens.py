"""Token generation must avoid original and generated collisions without rescans."""

from app.core import Span, mask, restore
import app.core as core


def test_generated_tokens_never_shadow_original_or_each_other(monkeypatch):
    a, b, c = "a" * 32, "b" * 32, "c" * 32
    existing = "{{EMAIL:" + a + "}}"
    original = existing + " x@example.com y@example.com"
    values = ["x@example.com", "y@example.com"]
    spans = [
        Span(original.index(v), original.index(v) + len(v), "EMAIL", v) for v in values
    ]
    # First draw collides with source, third with a previous replacement.
    draws = iter([a, b, b, c])
    monkeypatch.setattr(core, "_random_hex", lambda: next(draws))
    result = mask(original, spans)
    assert existing not in result.mapping
    assert set(result.mapping) == {"{{EMAIL:" + b + "}}", "{{EMAIL:" + c + "}}"}
    assert restore(result.masked_text, result.mapping) == original


def test_dense_values_and_unicode_offsets_remain_exact():
    original = "ёж x@example.com; " * 2000
    spans = []
    start = 0
    while (start := original.find("x@example.com", start)) != -1:
        spans.append(Span(start, start + 13, "EMAIL", original[start : start + 13]))
        start += 13
    result = mask(original, spans)
    assert len(result.mapping) == 2000
    assert "x@example.com" not in result.masked_text
    assert restore(result.masked_text, result.mapping) == original


def test_span_type_must_fit_restorable_token_grammar():
    import pytest

    for kind in ("lowercase", "TYPE:INJECTION", "A" * 41):
        with pytest.raises(ValueError, match="span type"):
            Span(0, 1, kind, "x")
