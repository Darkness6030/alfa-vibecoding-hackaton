"""Shared lexical boundaries; offsets always refer to the untouched input."""

# Possessive whitespace cannot be redistributed on a failed value match.
SEPARATOR = r"\s*+(?:[:—-]\s*+)?"
HORIZONTAL = r"[ \t\u00a0\u202f]"
WORD = r"[^\W\d_]++(?:[-'’][^\W\d_]++)*"
STOP = (
    r"(?:обратился|обратилась|работает|родился|родилась|из|дата|паспорт|телефон|"
    r"почта|проживает|гражданство|подписал|и|в|с|на|по|адрес|выдан|код|"
    r"customer|client|passport|phone|telephone|mobile|email|address|city|country|postcode|date|dob|citizenship|nationality|"
    r"issued|issue|department|division|cvv|cvc|pin|card|born|lives|works|called|"
    r"requested|signed|and|has|is|was|with)\b"
)
VALUE_WORD = rf"(?!{STOP}){WORD}"


def words(maximum: int = 4) -> str:
    """A field value with explicit sentence/next-field boundaries."""
    return rf"{VALUE_WORD}(?:{HORIZONTAL}++{VALUE_WORD}){{0,{maximum - 1}}}"
