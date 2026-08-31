"""LLM provider seam.

One protocol, two implementations. Claude is the primary (Agent Studio's own
stack); Gemini Flash's free tier is the zero-cost fallback so the demo can
run at Rs 0 if credits run dry mid-buildathon.

Providers return raw text. Parsing and schema validation happen once, in
diagnose.py, so a provider swap cannot change the validation behaviour.
"""

from typing import Protocol


class LLMProvider(Protocol):
    """Anything that can turn a system + user prompt into text."""

    name: str

    def complete(self, system: str, user: str) -> str:
        """Return the model's raw text response.

        Should request JSON output where the provider supports a structured
        or JSON mode, but must not assume it succeeded — diagnose.py validates
        regardless.

        Raises:
            LLMUnavailable: on transport failure, rate limit, or auth error,
                so diagnose.py can fall back to the secondary provider rather
                than escalating a case for an infrastructure reason.
        """
        ...


class LLMUnavailable(RuntimeError):
    """Provider could not be reached or refused the request.

    Distinct from "model returned something invalid" — that escalates the
    case; this one retries on the fallback provider first.
    """


class AnthropicProvider:
    """Primary. Claude via the `anthropic` SDK.

    Model id lives in config (settings.anthropic_model) rather than here, so
    it can be bumped without a code change.
    """

    name = "anthropic"

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError("step-04: Anthropic provider")


class GeminiProvider:
    """Zero-cost fallback. Gemini Flash free tier.

    Selected automatically when the primary raises LLMUnavailable, or forced
    via settings.llm_provider for a Rs 0 demo run.
    """

    name = "gemini"

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError("step-04: Gemini fallback provider")


def get_provider(name: str | None = None) -> LLMProvider:
    """Resolve the configured provider, defaulting to settings.llm_provider."""
    raise NotImplementedError("step-04: provider selection")
