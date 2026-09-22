"""Demo proxy service (K6).

Flow: consumer text -> detect/mask (tokens) -> mock LLM -> detokenize response
-> return to consumer. Uses the same core and policies as /process.

Detokenization of a modified LLM response: whole tokens are restored wherever
they appear (moved tokens work). Unknown/corrupted tokens are left as-is, never
restored randomly. A mock/LLM error never leaks the source text.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core import restore
from app.engine import MaskingEngine
from app.llm import LLM, LLMError


class ProxyError(Exception):
    """LLM failed; the source must not be leaked."""


@dataclass(frozen=True)
class ProxyResult:
    masked_input: str
    llm_response: str
    restored_response: str


class ProxyService:
    def __init__(self, engine: MaskingEngine, llm: LLM) -> None:
        self._engine = engine
        self._llm = llm

    def run(self, text: str) -> ProxyResult:
        # Mask the input: only tokens cross the LLM boundary.
        masked = self._engine.mask(text)
        try:
            llm_response = self._llm.generate(masked.masked_text)
        except LLMError as exc:
            raise ProxyError("llm unavailable") from exc

        # Detokenize the LLM response using the mapping. Unknown/corrupted
        # tokens are left as-is.
        restored = restore(llm_response, masked.mapping)
        return ProxyResult(
            masked_input=masked.masked_text,
            llm_response=llm_response,
            restored_response=restored,
        )