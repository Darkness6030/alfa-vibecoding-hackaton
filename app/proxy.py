"""Demo proxy service (K6).

Flow: consumer text -> detect/mask (tokens) -> mock LLM -> detokenize response
-> return to consumer. Uses the same core and policies as /process.

Detokenization of a modified LLM response: whole tokens are restored wherever
they appear (moved tokens work). Unknown/corrupted tokens are left as-is, never
restored randomly. A mock/LLM error never leaks the source text.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from app.metrics import measured

from app.core import mask, restore, TOKEN_RE
from app.engine import MaskingEngine
from app.llm import LLM, LLMError


class ProxyError(Exception):
    """LLM failed; the source must not be leaked."""


@dataclass(frozen=True)
class ProxyResult:
    masked_input: str
    llm_response: str
    restored_response: str
    warnings: tuple[str, ...] = ()


class ProxyService:
    def __init__(self, engine: MaskingEngine, llm: LLM) -> None:
        self._engine = engine
        self._llm = llm

    def run(self, text: str) -> ProxyResult:
        # Mask the input: only tokens cross the LLM boundary.
        masked = self._engine.mask(text)
        logging.getLogger("alfagen").info(
            "stage=proxy_types types=%s", ",".join(sorted(masked.detected_types))
        )
        try:
            with measured("llm_mock"):
                llm_response = self._llm.generate(masked.masked_text)
        except LLMError as exc:
            raise ProxyError("llm unavailable") from exc

        # Detokenize the LLM response using the mapping. Unknown/corrupted
        # tokens are left as-is.
        # Re-scan generated content while protecting the already issued tokens.
        token_values = {m.group() for m in TOKEN_RE.finditer(llm_response)}
        unknown = token_values - masked.mapping.keys()
        protected = [(m.start(), m.end()) for m in TOKEN_RE.finditer(llm_response)]

        spans = [
            s
            for s in self._engine.detect(llm_response)
            if not any(s.start < end and start < s.end for start, end in protected)
        ]
        safe_response = mask(llm_response, spans).masked_text
        warnings = []
        if unknown or any(token not in llm_response for token in masked.mapping):
            warnings.append("unknown_or_missing_tokens")
        if spans:
            warnings.append("new_sensitive_content_masked")
        with measured("restore"):
            restored = restore(safe_response, masked.mapping)
        return ProxyResult(
            masked_input=masked.masked_text,
            llm_response=safe_response,
            restored_response=restored,
            warnings=tuple(warnings),
        )
