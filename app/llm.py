"""LLM adapter interface and explicit mock (K6).

The runtime LLM is a stub by participant decision (D06). The mock is explicitly
labeled and returns a modified environment/order of whole tokens so the proxy
can demonstrate real detokenization, not just echo.

Test modes:
- ``reorder`` (default): moves whole tokens to a different order.
- ``timeout``: raises a timeout error (mock failure must not leak the source).
- ``corrupt``: returns a text with a corrupted/unknown token.
"""

from __future__ import annotations

from app.core import TOKEN_RE as _TOKEN_RE
from typing import Protocol


class LLMError(Exception):
    """LLM call failed (timeout, network, etc.)."""


class LLM(Protocol):
    """Interface every LLM adapter implements."""

    def generate(self, masked_text: str) -> str:
        """Return a generated response for the masked text."""
        ...


class MockLLM:
    """Deterministic mock LLM. Explicitly a stub, not real generation."""

    def __init__(self, mode: str = "reorder") -> None:
        self.mode = mode

    def generate(self, masked_text: str) -> str:
        if self.mode == "timeout":
            raise LLMError("mock timeout")
        if self.mode == "corrupt":
            return self._corrupt(masked_text)
        return self._reorder(masked_text)

    def _reorder(self, masked_text: str) -> str:
        """Return a response with whole tokens moved to a different order."""
        tokens = _TOKEN_RE.findall(masked_text)
        if not tokens:
            return "Ответ: текст без персональных данных."
        # Move tokens to the end in reverse order to demonstrate detokenization
        # of moved tokens.
        body = _TOKEN_RE.sub("", masked_text).strip()
        moved = ", ".join(reversed(tokens))
        return f"Ответ: {body} [токены: {moved}]"

    def _corrupt(self, masked_text: str) -> str:
        """Return a response with a corrupted (unknown) token."""
        tokens = _TOKEN_RE.findall(masked_text)
        if not tokens:
            return "Ответ: текст без персональных данных."
        # Corrupt the first token (truncate it) so it is no longer recognized.
        corrupted = tokens[0][:-4] + "xxxx"
        body = _TOKEN_RE.sub("", masked_text).strip()
        return f"Ответ: {body} [повреждённый токен: {corrupted}]"
