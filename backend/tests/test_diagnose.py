"""Diagnosis tests — no database, no network.

diagnose() takes explicit `provider`/`fallback_provider` arguments precisely
so these tests can hand it stub implementations of the LLMProvider protocol
instead of hitting Groq, Anthropic, or Gemini. What's verified here is the
parse/retry/fallback plumbing around a provider, not any specific model's
output — that a real model reliably fills the schema was confirmed
separately, live against Groq and Gemini (see corrections.md, entry 9).
`anthropic` remains uninstalled/unverified, as it is not the default.
"""

import pytest

from app.agent.diagnose import MAX_PARSE_RETRIES, DiagnosisFailed, diagnose
from app.agent.prompts import DEMO_LOOSE_SYSTEM_PROMPT, SYSTEM_PROMPT
from app.agent.providers import LLMUnavailable
from app.schemas.proposal import ActionKind

CASE_CONTEXT = {
    "case_id": "case_test",
    "failure_class": "SOFT_FUNDS",
    "amount_paise": 149_900,
    "method": "upi",
    "is_mandate": False,
    "attempts_used": 1,
    "max_attempts": 4,
    "messages_sent": 0,
    "max_messages": 3,
    "last_contact_at": None,
    "now": "2026-09-02T12:00:00+05:30",
}

VALID_JSON = '{"action": "SCHEDULE_RETRY", "confidence": 0.9, "reasoning": "Looks recoverable."}'


class _RecordingProvider:
    """Records every (system, user) pair it was called with, then returns
    canned responses in order — one per call, repeating the last for any
    call beyond what was supplied."""

    name = "recording"

    def __init__(self, *responses: str | Exception):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        response = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(response, Exception):
            raise response
        return response


def test_happy_path_returns_a_validated_proposal():
    provider = _RecordingProvider(VALID_JSON)

    proposal = diagnose(CASE_CONTEXT, provider=provider)

    assert proposal.action == ActionKind.SCHEDULE_RETRY
    assert proposal.confidence == 0.9
    assert len(provider.calls) == 1


def test_normal_prompt_uses_system_prompt_not_the_loose_variant():
    provider = _RecordingProvider(VALID_JSON)

    diagnose(CASE_CONTEXT, provider=provider, loose_prompt=False)

    system_sent, _ = provider.calls[0]
    assert system_sent == SYSTEM_PROMPT


def test_loose_prompt_uses_the_demo_variant():
    provider = _RecordingProvider(VALID_JSON)

    diagnose(CASE_CONTEXT, provider=provider, loose_prompt=True)

    system_sent, _ = provider.calls[0]
    assert system_sent == DEMO_LOOSE_SYSTEM_PROMPT
    assert "unrecoverable" not in system_sent.lower()


def test_malformed_output_is_retried_once_then_escalates():
    provider = _RecordingProvider("not json at all", "still not json")

    with pytest.raises(DiagnosisFailed):
        diagnose(CASE_CONTEXT, provider=provider, fallback_provider=provider)

    assert len(provider.calls) == MAX_PARSE_RETRIES + 1


def test_malformed_output_recovers_on_the_repair_retry():
    provider = _RecordingProvider("not json at all", VALID_JSON)

    proposal = diagnose(CASE_CONTEXT, provider=provider)

    assert proposal.action == ActionKind.SCHEDULE_RETRY
    assert len(provider.calls) == 2
    # The repair turn must include the validation error, not just repeat
    # the original prompt verbatim.
    _, second_user = provider.calls[1]
    assert "previous response was invalid" in second_user


def test_schema_violation_is_retried_same_as_malformed_json():
    """A syntactically valid JSON object that violates the schema (bad
    action, out-of-range confidence) is a repair-retry case too, not a
    different failure path."""
    bad_schema = '{"action": "NOT_A_REAL_ACTION", "confidence": 0.9, "reasoning": "x"}'
    provider = _RecordingProvider(bad_schema, VALID_JSON)

    proposal = diagnose(CASE_CONTEXT, provider=provider)

    assert proposal.action == ActionKind.SCHEDULE_RETRY
    assert len(provider.calls) == 2


def test_primary_unavailable_falls_back_to_secondary():
    primary = _RecordingProvider(LLMUnavailable("primary down"))
    secondary = _RecordingProvider(VALID_JSON)

    proposal = diagnose(CASE_CONTEXT, provider=primary, fallback_provider=secondary)

    assert proposal.action == ActionKind.SCHEDULE_RETRY
    assert len(primary.calls) == 1
    assert len(secondary.calls) == 1


def test_both_providers_unavailable_escalates():
    primary = _RecordingProvider(LLMUnavailable("primary down"))
    secondary = _RecordingProvider(LLMUnavailable("secondary down"))

    with pytest.raises(DiagnosisFailed):
        diagnose(CASE_CONTEXT, provider=primary, fallback_provider=secondary)
