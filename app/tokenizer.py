"""Declared tokenizer for TPS and large-text accounting (K8).

The tokenizer is a simple whitespace/punctuation splitter. It is declared so
TPS and the 100k-token requirement are measured against a known definition.
This is NOT a subword/LLM tokenizer; it is a technical accounting unit.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"\S+")


def count_tokens(text: str) -> int:
    """Count tokens as whitespace-delimited runs of non-space characters."""
    return len(_TOKEN_RE.findall(text))
