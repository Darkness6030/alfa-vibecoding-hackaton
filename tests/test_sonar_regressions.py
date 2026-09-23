"""Behavioral guards for Sonar fixes: permissions, offsets and regex boundaries."""

import json
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.detectors.address import AddressDetector
from app.detectors.base import RegexDetector, context_before, context_before_offset
from app.detectors.ner import NerDetector, _NatashaPipeline
from app.detectors.phone import PhoneDetector
from app.policy import ALL_TYPES, SystemPolicy, load_policy


@pytest.mark.parametrize("attribute", ["detect_types", "mask_types"])
@pytest.mark.parametrize("types", [["UNKNOWN"], ["EMAIL", "UNKNOWN"]])
def test_policy_rejects_unknown_types_in_incomparable_sets(tmp_path, attribute, types):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"systems": {"crm": {attribute: types}}}))
    with pytest.raises(ValueError, match="unknown type"):
        load_policy(str(path), "demo-secure")


@pytest.mark.parametrize("mask_types", [["PHONE"], ["PHONE", "PERSON"]])
def test_policy_rejects_incomparable_detect_and_mask_sets(tmp_path, mask_types):
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps(
            {
                "systems": {
                    "crm": {
                        "detect_types": ["EMAIL", "PERSON"],
                        "mask_types": mask_types,
                    }
                }
            }
        )
    )
    with pytest.raises(ValueError, match="masked types must be detected"):
        load_policy(str(path), "demo-secure")


def test_proxy_rejects_incomparable_detect_and_mask_sets(monkeypatch):
    import app.main as main

    monkeypatch.setitem(
        main.policy.systems,
        "crm",
        SystemPolicy(
            name="crm",
            api_key="test-crm-only",
            demask_allowed=True,
            detect_types=ALL_TYPES | {"EXTRA_DETECT"},
            mask_types=ALL_TYPES | {"EXTRA_MASK"},
        ),
    )
    with TestClient(main.app) as client:
        response = client.post(
            "/proxy",
            headers={"X-API-Key": "test-crm-only"},
            json={"payload": "safe", "payload_id": "sets"},
        )
    assert response.status_code == 403
    assert response.json() == {"detail": "forbidden"}


@pytest.mark.parametrize(
    "label,value",
    [
        ("г.", "Москва"),
        ("город.", "Москва"),
        ("ул.", "Маросейка"),
        ("улица.", "Маросейка"),
        ("пр-т.", "Мира"),
        ("д.", "5"),
        ("дом.", "5"),
        ("кв.", "9"),
        ("квартира.", "9"),
        ("корп.", "2"),
        ("корпус.", "2"),
        ("стр.", "1"),
        ("строение.", "1"),
        ("индекс:", "101000"),
    ],
)
def test_address_labels_and_punctuation_stay_outside_sensitive_span(label, value):
    text = f"Адрес: {label}  {value}"
    spans = AddressDetector().detect(text)
    assert spans
    assert all(
        s.value == value
        and s.start == text.index(value)
        and text[s.start : s.end] == value
        for s in spans
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Phone: +1 212 555 0198", ["+1 212 555 0198"]),
        ("Phone: +١ ٢١٢ ٥٥٥ ٠١٩٨", []),
        ("Phone: +１ ２１２ ５５５ ０１９８", []),
        ("Phone: +1 212 555 0198١", []),
        ("Phone: я+1 212 555 0198", []),
    ],
)
def test_international_phone_keeps_ascii_digits_and_unicode_boundaries(text, expected):
    assert [s.value for s in PhoneDetector().detect(text)] == expected


def test_unconfigured_regex_detector_does_not_detect_empty_or_nonempty_text():
    assert RegexDetector().detect("") == []
    assert RegexDetector().detect("Клиент John Smith, a@b.com") == []


def test_ner_pipeline_preserves_offsets_and_context_filter(monkeypatch):
    text = "😀 Клиент Иван Петров. Поэт Александр Пушкин. Клиент проживает Москва"
    values = [("Иван Петров", "PER"), ("Александр Пушкин", "PER"), ("Москва", "LOC")]
    calls = []

    class FakeDoc:
        def __init__(self, source):
            assert source == text
            self.spans = [
                SimpleNamespace(
                    start=text.index(value),
                    stop=text.index(value) + len(value),
                    type=kind,
                )
                for value, kind in values
            ]

        def segment(self, segmenter):
            calls.append(segmenter)

        def tag_morph(self, tagger):
            calls.append(tagger)

        def tag_ner(self, tagger):
            calls.append(tagger)

    monkeypatch.setattr(
        _NatashaPipeline, "get", lambda: ("segment", "morph", "ner", FakeDoc)
    )
    spans = NerDetector().detect(text)
    # The six-word context still includes "поэт" for the last location.
    assert [(s.type, s.value) for s in spans] == [("PERSON", "Иван Петров")]
    assert calls == ["segment", "morph", "ner"]
    assert all(text[s.start : s.end] == s.value for s in spans)


@pytest.mark.parametrize("prefix", ["", "😀 Клиент: ", "слово " * 100 + "Клиент: "])
def test_regex_and_ner_share_the_same_context_window(prefix):
    text = prefix + "Иван"
    match = re.search("Иван", text)
    assert context_before(text, match, 6) == context_before_offset(
        text, match.start(), 6
    )
