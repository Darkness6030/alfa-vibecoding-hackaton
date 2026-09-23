"""K4a benchmark: measure natasha/slovnet/navec NER quality, time, memory.

Runs the NER pipeline over the synthetic set, computes PER/LOC precision/recall
against known spans, and measures wall time and peak memory. Also runs a simple
regex baseline for comparison.

Usage:
    python benchmarks/run_ner_benchmark.py
"""

from __future__ import annotations

import re
import sys
import time
import tracemalloc

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from synthetic_ner import build_dataset


def run_natasha(texts: list[str]):
    """Run natasha NER over texts, return list of (type, start, end) per text."""
    from natasha import Doc, Segmenter, NewsEmbedding, NewsMorphTagger, NewsNERTagger

    segmenter = Segmenter()
    emb = NewsEmbedding()
    morph_tagger = NewsMorphTagger(emb)
    ner_tagger = NewsNERTagger(emb)

    results = []
    for text in texts:
        doc = Doc(text)
        doc.segment(segmenter)
        doc.tag_morph(morph_tagger)
        doc.tag_ner(ner_tagger)
        spans = []
        for span in doc.spans:
            if span.type in ("PER", "LOC"):
                spans.append((span.type, span.start, span.stop))
        results.append(spans)
    return results


def run_regex(texts: list[str]):
    """Simple regex baseline: capitalized word sequences as PER, known cities as LOC."""
    city_re = re.compile(
        r"(Москв\w+|Санкт-Петербург\w*|Казан\w+|Новосибирск\w+|Екатеринбург\w+)"
    )
    name_re = re.compile(r"\b([А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+)\b")
    results = []
    for text in texts:
        spans = []
        for m in city_re.finditer(text):
            spans.append(("LOC", m.start(), m.end()))
        for m in name_re.finditer(text):
            spans.append(("PER", m.start(), m.end()))
        results.append(spans)
    return results


def evaluate(predicted, expected):
    """Compute per-type precision/recall/F1 over exact span matches.

    ``expected`` is a list of (per_spans, loc_spans) tuples per text.
    """
    stats = {}
    for typ in ("PER", "LOC"):
        idx = 0 if typ == "PER" else 1
        tp = fp = fn = 0
        for pred, exp in zip(predicted, expected, strict=True):
            pred_set = {(s, e) for t, s, e in pred if t == typ}
            exp_set = set(exp[idx])
            tp += len(pred_set & exp_set)
            fp += len(pred_set - exp_set)
            fn += len(exp_set - pred_set)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        stats[typ] = {"precision": prec, "recall": rec, "f1": f1}
    return stats


def measure(fn, texts):
    tracemalloc.start()
    t0 = time.perf_counter()
    result = fn(texts)
    elapsed = time.perf_counter() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, elapsed, peak


def main() -> None:
    dataset = build_dataset()
    texts = [c[0] for c in dataset]
    expected = [(c[1], c[2]) for c in dataset]

    print(f"dataset: {len(dataset)} cases")

    print("\n=== natasha NER ===")
    try:
        pred, elapsed, peak = measure(run_natasha, texts)
        stats = evaluate(pred, expected)
        print(f"time: {elapsed:.3f}s  peak_mem: {peak / 1e6:.1f} MB")
        for typ, s in stats.items():
            print(
                f"  {typ}: P={s['precision']:.2f} R={s['recall']:.2f} F1={s['f1']:.2f}"
            )
    except Exception as exc:  # pragma: no cover
        import traceback

        traceback.print_exc()
        print(f"natasha failed: {type(exc).__name__}: {exc}")

    print("\n=== regex baseline ===")
    pred, elapsed, peak = measure(run_regex, texts)
    stats = evaluate(pred, expected)
    print(f"time: {elapsed:.3f}s  peak_mem: {peak / 1e6:.1f} MB")
    for typ, s in stats.items():
        print(f"  {typ}: P={s['precision']:.2f} R={s['recall']:.2f} F1={s['f1']:.2f}")


if __name__ == "__main__":
    main()
