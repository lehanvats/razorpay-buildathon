"""GroqProvider unit tests — no network.

Mocks the groq SDK's client construction and completions.create so these
exercise complete()'s error-classification logic (which failures map to
LLMUnavailable, and which don't) without a real API key or network access.
The other two providers (Anthropic, Gemini) predate this file and are
covered only indirectly through test_diagnose.py's stub-provider tests —
Groq gets a dedicated file because it is now the default primary and its
error paths (empty choices, truncated output) are the ones a prior review
found unguarded.
"""

import sys
import types

import httpx
import pytest

from app.agent.providers import GroqProvider, LLMUnavailable


def _fake_choice(content: str | None, finish_reason: str = "stop"):
    message = types.SimpleNamespace(content=content)
    return types.SimpleNamespace(message=message, finish_reason=finish_reason)


def _fake_response(choices: list):
    return types.SimpleNamespace(choices=choices)


def _patch_client(monkeypatch, create_fn):
    """Replace groq.Groq with a stub whose chat.completions.create is create_fn."""
    import groq

    class _FakeClient:
        def __init__(self, api_key):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=lambda **kw: create_fn(**kw))
            )

    monkeypatch.setattr(groq, "Groq", _FakeClient)


def test_missing_api_key_raises_llm_unavailable(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "")

    with pytest.raises(LLMUnavailable, match="GROQ_API_KEY"):
        GroqProvider().complete("system", "user")


def test_uninstalled_sdk_raises_llm_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "groq", None)

    with pytest.raises(LLMUnavailable, match="groq SDK is not installed"):
        GroqProvider().complete("system", "user")


def test_api_error_raises_llm_unavailable(monkeypatch):
    import groq

    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test_key")

    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")

    def _raise(**kw):
        raise groq.APIError("boom", request, body=None)

    _patch_client(monkeypatch, _raise)

    with pytest.raises(LLMUnavailable, match="Groq request failed"):
        GroqProvider().complete("system", "user")


def test_happy_path_returns_content(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test_key")
    _patch_client(monkeypatch, lambda **kw: _fake_response([_fake_choice("hello")]))

    assert GroqProvider().complete("system", "user") == "hello"


def test_empty_choices_raises_llm_unavailable(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test_key")
    _patch_client(monkeypatch, lambda **kw: _fake_response([]))

    with pytest.raises(LLMUnavailable, match="no choices"):
        GroqProvider().complete("system", "user")


def test_truncated_empty_content_raises_llm_unavailable(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test_key")
    _patch_client(
        monkeypatch,
        lambda **kw: _fake_response([_fake_choice(None, finish_reason="length")]),
    )

    with pytest.raises(LLMUnavailable, match="truncated"):
        GroqProvider().complete("system", "user")


def test_empty_content_without_truncation_passes_through(monkeypatch):
    """finish_reason="stop" with empty content is unusual but not a transport
    failure — diagnose()'s parse/repair loop should see it and fail on
    "invalid JSON" rather than get silently misrouted to LLMUnavailable."""
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test_key")
    _patch_client(
        monkeypatch,
        lambda **kw: _fake_response([_fake_choice("", finish_reason="stop")]),
    )

    assert GroqProvider().complete("system", "user") == ""
