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


def test_truncated_partial_content_raises_llm_unavailable(monkeypatch):
    """The real case (ab9f88a6, 2026-09-05): the budget ran out partway
    through the JSON. A cut-off proposal can never parse, and handing it to
    diagnose() burns the one repair retry against the same budget — so it
    must be routed to the fallback provider, exactly like the empty case."""
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test_key")
    partial = '{\n  "action": "SCHEDULE_RETRY",\n  "timing": "2026-09-05T09:00:00+05:30",\n  "conf'
    _patch_client(
        monkeypatch,
        lambda **kw: _fake_response([_fake_choice(partial, finish_reason="length")]),
    )

    with pytest.raises(LLMUnavailable, match="truncated"):
        GroqProvider().complete("system", "user")


def test_gpt_oss_models_get_low_reasoning_effort_and_the_shared_budget(monkeypatch):
    from app.agent.providers import _MAX_TOKENS
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test_key")
    monkeypatch.setattr(settings, "groq_model", "openai/gpt-oss-120b")
    captured: dict = {}

    def _create(**kw):
        captured.update(kw)
        return _fake_response([_fake_choice("{}")])

    _patch_client(monkeypatch, _create)
    GroqProvider().complete("system", "user")

    assert captured["reasoning_effort"] == "low"
    assert captured["max_completion_tokens"] == _MAX_TOKENS
    assert "max_tokens" not in captured  # the deprecated alias is not sent alongside
    assert captured["response_format"] == {"type": "json_object"}


def test_non_reasoning_models_are_not_sent_reasoning_effort(monkeypatch):
    """Groq rejects `reasoning_effort` on models that don't reason, so a
    configured non-gpt-oss model must not get it."""
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test_key")
    monkeypatch.setattr(settings, "groq_model", "llama-3.3-70b-versatile")
    captured: dict = {}

    def _create(**kw):
        captured.update(kw)
        return _fake_response([_fake_choice("{}")])

    _patch_client(monkeypatch, _create)
    GroqProvider().complete("system", "user")

    assert "reasoning_effort" not in captured


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
