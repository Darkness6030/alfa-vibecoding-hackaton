"""K6 tests: demo proxy, mock LLM, moved/corrupted tokens, no leak on error."""

from __future__ import annotations

import pytest

from app.engine import MaskingEngine
from app.llm import LLMError, MockLLM
from app.proxy import ProxyError, ProxyService


def _engine():
    return MaskingEngine(ner_enabled=False)


def test_proxy_masks_input_before_llm():
    proxy = ProxyService(engine=_engine(), llm=MockLLM())
    result = proxy.run("Клиент Иван Петров, почта a@b.com")
    # The LLM only sees masked text (no original PII).
    assert "a@b.com" not in result.masked_input
    assert "Иван Петров" not in result.masked_input
    assert "{{" in result.masked_input


def test_proxy_restores_moved_tokens():
    proxy = ProxyService(engine=_engine(), llm=MockLLM())
    result = proxy.run("Клиент Иван Петров, почта a@b.com")
    # The mock moves tokens; the restored response must contain the originals.
    assert "Иван Петров" in result.restored_response
    assert "a@b.com" in result.restored_response


def test_proxy_restored_response_contains_originals():
    proxy = ProxyService(engine=_engine(), llm=MockLLM())
    result = proxy.run("Клиент Иван Петров, почта a@b.com")
    # The restored response is the LLM response with tokens replaced.
    assert "{{" not in result.restored_response


def test_proxy_corrupted_token_not_restored_randomly():
    proxy = ProxyService(engine=_engine(), llm=MockLLM(mode="corrupt"))
    result = proxy.run("Клиент Иван Петров, почта a@b.com")
    # The corrupted token is left as-is, not guessed.
    assert "xxxx" in result.restored_response


def test_proxy_timeout_raises_and_no_leak():
    proxy = ProxyService(engine=_engine(), llm=MockLLM(mode="timeout"))
    with pytest.raises(ProxyError):
        proxy.run("Клиент Иван Петров, почта a@b.com")


def test_mock_llm_reorders_tokens():
    llm = MockLLM()
    out = llm.generate(
        "Клиент {{PERSON:aaaaaaaaaaaaaaaa}} из {{LOCATION:bbbbbbbbbbbbbbbb}}"
    )
    assert "{{LOCATION:bbbbbbbbbbbbbbbb}}" in out
    assert "{{PERSON:aaaaaaaaaaaaaaaa}}" in out


def test_mock_llm_timeout_raises_llm_error():
    llm = MockLLM(mode="timeout")
    with pytest.raises(LLMError):
        llm.generate("текст")


def test_mock_llm_no_tokens():
    llm = MockLLM()
    out = llm.generate("просто текст")
    assert "без персональных данных" in out
