"""Contextual address components and labelled birth places."""

import re
from app.detectors.base import RegexDetector, context_before
from app.core import Span
from app.detectors.language import SEPARATOR, VALUE_WORD, HORIZONTAL, words

_ADDRESS_WORD = rf"(?!(?:город|г|улица|ул|пр-т|дом|д|квартира|кв|корпус|корп|строение|стр|индекс)\b){VALUE_WORD}"
_WORD = rf"{_ADDRESS_WORD}(?:{HORIZONTAL}++{_ADDRESS_WORD}){{0,4}}"
_PART = rf"(?:г(?:ород)?\.?\s*{_WORD}|ул(?:ица)?\.?\s*(?:\d+[ -])?{_WORD}|пр-т\.?\s*{_WORD}|д(?:ом)?\.?\s*\d+[а-яa-z/\d-]*|кв(?:артира)?\.?\s*\d+|(?:корп(?:ус)?|стр(?:оение)?)\.?\s*\d+[а-яa-z/\d-]*|индекс\s*:?\s*\d{{6}})"
_ADDRESS_RE = re.compile(rf"(?<!\w){_PART}(?:(?:\s*,\s*|\s+){_PART})*", re.IGNORECASE)
_COMPONENT_RE = re.compile(_PART, re.IGNORECASE)
_LABEL_RE = re.compile(
    r"^(?:город|г|улица|ул|пр-т|дом|д|квартира|кв|корпус|корп|строение|стр|индекс)\.?\s*:?\s*",
    re.IGNORECASE,
)
_POSITIVE = (
    "адрес",
    "прожива",
    "зарегистрирован",
    "место жительства",
    "address",
    "resides",
    "lives",
)
_NEGATIVE = ("отделени", "филиал", "офис", "bank branch", "office")
# Individually supplied country, postal code, city or street are required too.
_LABELLED_VALUE_RE = re.compile(
    rf"\b(?:страна|город|улица|дом|квартира|корпус|строение|country|city|street|house|apartment)\b\s*+:\s*+"
    rf"(?P<value>\d+[a-zа-я]?(?:[/-]\d+[a-zа-я]?)*|{_WORD})",
    re.IGNORECASE,
)
_LABELLED_STREET_RE = re.compile(
    rf"\b(?:улица|street)\s*+:\s*+(?P<value>(?:\d++[- ]?)?{_WORD})",
    re.IGNORECASE,
)
_POSTCODE_RE = re.compile(
    r"\b(?:индекс|postcode|postal code|zip(?: code)?)\s*+:\s*+"
    r"(?P<value>[a-z]{1,2}\d[a-z\d]?[ \t]*\d[a-z]{2}|"
    r"[a-z]\d[a-z][ \t]*\d[a-z]\d|\d{5}(?:-\d{4})?|\d{6})(?![\w-])",
    re.IGNORECASE,
)
_EN_STREET_RE = re.compile(
    rf"(?<!\w)(?P<house>\d++[a-z]?)\s++(?P<street>{words(5)})[ \t]++"
    rf"(?:street|st\.?|road|rd\.?|avenue|ave\.?|lane|ln\.?|drive|dr\.?)\b"
    rf"(?:,[ \t]*+(?P<city>{words(4)}))?",
    re.IGNORECASE,
)
_RESIDENCE_RE = re.compile(
    rf"\b(?:прожива(?:ет|ю)|жив[её]т|lives|resides)\s++(?:в|in|at)\s++(?P<value>{words(4)})",
    re.I,
)


def _public_context(text, match):
    before = context_before(text, match, 12)
    negative = max((before.rfind(k) for k in _NEGATIVE), default=-1)
    personal = max(
        (
            before.rfind(k)
            for k in ("клиент", "домашн", "прожив", "customer", "home", "residential")
        ),
        default=-1,
    )
    return negative >= 0 and personal <= negative


class AddressDetector(RegexDetector):
    type = "ADDRESS"
    pattern = _ADDRESS_RE
    priority = 30

    def validate(self, text, match):
        before = context_before(text, match, 10)
        if _public_context(text, match):
            return False
        # A structured multi-component address (e.g. "г. X, ул. Y, д. Z") is an
        # address even without an explicit "Адрес:" label.
        components = list(_COMPONENT_RE.finditer(match.group()))
        if len(components) >= 2:
            return True
        # Otherwise require a personal address context word.
        return any(k in before for k in _POSITIVE)

    def detect(self, text):
        spans = []
        for match in self.pattern.finditer(text):
            if not self.validate(text, match):
                continue
            for component in _COMPONENT_RE.finditer(match.group()):
                label = _LABEL_RE.match(component.group())
                start = match.start() + component.start() + label.end()
                end = match.start() + component.end()
                spans.append(
                    Span(start, end, self.type, text[start:end], self.priority)
                )
        spans.extend(self._labelled_spans(text))
        spans.extend(self._international_spans(text))
        return spans

    def _labelled_spans(self, text):
        spans = []
        # Individually supplied country, postal code, city or street are required too.
        for m in _LABELLED_VALUE_RE.finditer(text):
            if _public_context(text, m):
                continue
            value = m.group("value").rstrip(" .")
            if value:
                spans.append(
                    Span(
                        m.start("value"),
                        m.start("value") + len(value),
                        self.type,
                        value,
                        30,
                    )
                )
        return spans

    def _international_spans(self, text):
        spans = []
        for pattern, groups in (
            (_EN_STREET_RE, ("house", "street", "city")),
            (_POSTCODE_RE, ("value",)),
            (_LABELLED_STREET_RE, ("value",)),
            (_RESIDENCE_RE, ("value",)),
        ):
            for match in pattern.finditer(text):
                if _public_context(text, match):
                    continue
                for group in groups:
                    if match.group(group):
                        start, end = match.span(group)
                        spans.append(
                            Span(start, end, self.type, text[start:end], self.priority)
                        )
        return spans


class BirthPlaceDetector(RegexDetector):
    type = "BIRTH_PLACE"
    priority = 35
    pattern = re.compile(
        rf"\b(?:место\s++рождения|родил(?:ся|ась)\s++в|place\s++of\s++birth|birthplace|born\s++in)"
        rf"{SEPARATOR}(?:г\.\s*+)?(?P<value>{words(4)})",
        re.IGNORECASE,
    )
