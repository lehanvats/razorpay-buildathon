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
        # Imported lazily: `anthropic` is in requirements.txt but not every
        # dev environment has it installed, and a module-top import would
        # make this whole package unimportable (breaking diagnose.py, and
        # every test that touches it) on a machine that never calls Claude.
        try:
            import anthropic
        except ImportError as exc:
            raise LLMUnavailable("anthropic SDK is not installed") from exc

        from app.config import settings

        if not settings.anthropic_api_key:
            raise LLMUnavailable("ANTHROPIC_API_KEY is not configured")

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        try:
            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.APIError as exc:
            raise LLMUnavailable(f"Anthropic request failed: {exc}") from exc

        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )


class GeminiProvider:
    """Zero-cost fallback. Gemini Flash free tier.

    Selected automatically when the primary raises LLMUnavailable, or forced
    via settings.llm_provider for a Rs 0 demo run.
    """

    name = "gemini"

    def complete(self, system: str, user: str) -> str:
        # Lazy import — see AnthropicProvider.complete for why.
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise LLMUnavailable("google-genai SDK is not installed") from exc

        from app.config import settings

        if not settings.gemini_api_key:
            raise LLMUnavailable("GEMINI_API_KEY is not configured")

        client = genai.Client(api_key=settings.gemini_api_key)
        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=user,
                config=types.GenerateContentConfig(system_instruction=system),
            )
        except Exception as exc:
            # google-genai's own exception hierarchy covers transport, auth
            # and rate-limit failures; treated uniformly here per this
            # provider's contract — any of those should trigger a fallback,
            # not an escalation, and this is the last fallback in the chain.
            raise LLMUnavailable(f"Gemini request failed: {exc}") from exc

        return response.text


_PROVIDERS: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}


def get_provider(name: str | None = None) -> LLMProvider:
    """Resolve the configured provider, defaulting to settings.llm_provider."""
    from app.config import settings

    key = name or settings.llm_provider
    try:
        provider_cls = _PROVIDERS[key]
    except KeyError as exc:
        raise ValueError(
            f"Unknown LLM provider {key!r}; must be one of {sorted(_PROVIDERS)}"
        ) from exc
    return provider_cls()
