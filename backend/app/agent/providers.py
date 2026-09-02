"""LLM provider seam.

One protocol, several implementations. Groq (openai/gpt-oss-120b) is the
primary — fast and generous free tier; Gemini Flash's free tier is the
zero-cost fallback so the demo can run at Rs 0 if credits run dry
mid-buildathon. Anthropic is kept as a third option for anyone who'd rather
spend Claude credits than use Groq.

Providers return raw text. Parsing and schema validation happen once, in
diagnose.py, so a provider swap cannot change the validation behaviour.
"""

import importlib
from typing import Protocol


class LLMProvider(Protocol):
    """Anything that can turn a system + user prompt into text."""

    name: str
    fallback: str | None
    """Name of the provider diagnose.py should fall back to on
    LLMUnavailable, or None. Lives on the provider (not a separate table in
    diagnose.py) so it can't drift out of sync with _PROVIDERS below."""

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


def _import_sdk(sdk_label: str, *module_names: str):
    """Import each of `module_names`, or raise LLMUnavailable naming
    `sdk_label` if any is missing.

    Every provider's SDK is in requirements.txt but not every dev
    environment has it installed, and a module-top import would make this
    whole package unimportable (breaking diagnose.py, and every test that
    touches it) on a machine that never calls that provider — so each
    provider imports its SDK lazily, inside complete(), through this helper.
    """
    try:
        modules = tuple(importlib.import_module(name) for name in module_names)
    except ImportError as exc:
        raise LLMUnavailable(f"{sdk_label} SDK is not installed") from exc
    return modules[0] if len(modules) == 1 else modules


def _require_api_key(value: str, env_name: str) -> str:
    """Return `value`, or raise LLMUnavailable naming the missing env var."""
    if not value:
        raise LLMUnavailable(f"{env_name} is not configured")
    return value


_MAX_TOKENS = 1024
"""Shared response budget for providers whose SDK takes one. Kept in one
place because Groq's truncation guard below exists precisely because this
number can run out before any visible content is emitted — a bump here is
the fix, not a per-provider literal."""


class GroqProvider:
    """Primary. openai/gpt-oss-120b via Groq's OpenAI-compatible chat API.

    Model id lives in config (settings.groq_model) rather than here, so it
    can be bumped without a code change.
    """

    name = "groq"
    fallback = "gemini"
    """Gemini's free tier is the fallback for this paid-ish primary."""

    def complete(self, system: str, user: str) -> str:
        groq = _import_sdk("groq", "groq")

        from app.config import settings

        api_key = _require_api_key(settings.groq_api_key, "GROQ_API_KEY")

        client = groq.Groq(api_key=api_key)
        try:
            response = client.chat.completions.create(
                model=settings.groq_model,
                max_tokens=_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except groq.APIError as exc:
            raise LLMUnavailable(f"Groq request failed: {exc}") from exc

        if not response.choices:
            raise LLMUnavailable("Groq returned no choices")

        choice = response.choices[0]
        content = choice.message.content or ""
        if not content and choice.finish_reason == "length":
            # openai/gpt-oss-120b is a reasoning model: its hidden reasoning
            # tokens count against max_tokens, so a tight budget can exhaust
            # the whole response before any visible content is emitted.
            # Treated as LLMUnavailable (not "invalid JSON") so diagnose()
            # falls back to Gemini instead of burning its one repair retry
            # against the same budget pressure.
            raise LLMUnavailable(
                "Groq truncated the response before emitting any content "
                "(max_tokens likely exhausted by reasoning tokens)"
            )
        return content


class AnthropicProvider:
    """Claude via the `anthropic` SDK. Not the default — kept as an
    alternative for anyone who'd rather spend Claude credits than use Groq.

    Model id lives in config (settings.anthropic_model) rather than here, so
    it can be bumped without a code change.
    """

    name = "anthropic"
    fallback = "gemini"
    """Gemini's free tier is the fallback for this paid-ish primary."""

    def complete(self, system: str, user: str) -> str:
        anthropic = _import_sdk("anthropic", "anthropic")

        from app.config import settings

        api_key = _require_api_key(settings.anthropic_api_key, "ANTHROPIC_API_KEY")

        client = anthropic.Anthropic(api_key=api_key)
        try:
            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=_MAX_TOKENS,
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
    fallback = "groq"
    """Groq is Gemini's own fallback for the (rare) case someone configures
    Gemini as primary instead."""

    def complete(self, system: str, user: str) -> str:
        genai, types = _import_sdk("google-genai", "google.genai", "google.genai.types")

        from app.config import settings

        api_key = _require_api_key(settings.gemini_api_key, "GEMINI_API_KEY")

        client = genai.Client(api_key=api_key)
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
            # not an escalation.
            raise LLMUnavailable(f"Gemini request failed: {exc}") from exc

        return response.text


_PROVIDERS: dict[str, type[LLMProvider]] = {
    "groq": GroqProvider,
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
