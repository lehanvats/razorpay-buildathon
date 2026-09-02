"""Diagnosis — the LLM proposes, structurally.

Runs for treated cases only. Control cases never reach this module; that
check belongs upstream in services/case_manager.py so there is exactly one
place where the holdout is honoured.

The output of this module is a Proposal, which is *not* an instruction. It
goes to policy.gate.gate() and nowhere else. This module must not import any
executor.
"""

import json

from pydantic import ValidationError

from app.agent.prompts import DEMO_LOOSE_SYSTEM_PROMPT, SYSTEM_PROMPT, build_case_prompt
from app.agent.providers import LLMProvider, LLMUnavailable, get_provider
from app.schemas.proposal import Proposal

MAX_PARSE_RETRIES = 1
"""Free-form or schema-invalid output is retried exactly once with a
repair instruction, then the case escalates. A model that cannot fill the
schema twice does not get a third chance to improvise."""


def diagnose(
    case_context: dict,
    *,
    loose_prompt: bool = False,
    provider: LLMProvider | None = None,
    fallback_provider: LLMProvider | None = None,
) -> Proposal:
    """Ask the model for a structured proposal.

    Flow:
      1. Build system + user prompts (agent/prompts.py).
      2. Call the configured provider; on LLMUnavailable, fall back once to
         the secondary provider.
      3. Parse JSON and validate against Proposal. On failure, retry once
         with the validation error fed back, then raise DiagnosisFailed.

    Deliberately takes no `session` and writes no audit event itself — every
    other module in the recovery loop does, but this one stays DB-free on
    purpose (see tests/test_diagnose.py, which builds Proposals with no
    database at all). `services/case_manager.advance_case`, which already
    holds both the session and this call's outcome, writes LLM_PROPOSED /
    LLM_REJECTED instead.

    Args:
        case_context: flat dict of case facts; see prompts.build_case_prompt.
        loose_prompt: use the deliberately under-constrained demo prompt so
            the gate can be seen blocking a hard-decline retry. Never true in
            normal operation.
        provider: primary LLMProvider to use. Defaults to
            providers.get_provider() (settings.llm_provider). Exists as a
            parameter so tests can pass a hand-rolled stub instead of
            hitting the network.
        fallback_provider: secondary provider tried once if `provider`
            raises LLMUnavailable. Defaults to `provider.fallback`, resolved
            via providers.get_provider().

    Returns:
        A validated Proposal. Caller must pass it to the policy gate.

    Raises:
        DiagnosisFailed: model could not produce valid structured output —
            either both providers raised LLMUnavailable, or the model never
            filled the schema within MAX_PARSE_RETRIES repair attempts.
            Caller escalates the case either way — it does not act on a
            guess or a transport failure.
    """
    system = DEMO_LOOSE_SYSTEM_PROMPT if loose_prompt else SYSTEM_PROMPT
    user = build_case_prompt(case_context)

    primary = provider or get_provider()
    secondary = fallback_provider if fallback_provider is not None else _default_fallback(primary)

    attempt_user = user
    error: str | None = None

    for _ in range(MAX_PARSE_RETRIES + 1):
        raw = _complete_with_fallback(primary, secondary, system, attempt_user)
        if raw is None:
            raise DiagnosisFailed(
                f"case {case_context.get('case_id')}: no LLM provider available "
                "(primary and fallback both raised LLMUnavailable)"
            )

        proposal, error = _try_parse(raw)
        if proposal is not None:
            return proposal

        attempt_user = (
            f"{user}\n\nYour previous response was invalid: {error}\n"
            "Respond again with JSON matching the schema exactly, and "
            "nothing else."
        )

    raise DiagnosisFailed(
        f"case {case_context.get('case_id')}: model did not produce a "
        f"schema-valid proposal after {MAX_PARSE_RETRIES} repair retry: {error}"
    )


def _default_fallback(primary: LLMProvider) -> LLMProvider | None:
    """A sensible secondary for `primary`, so a transport failure on the
    primary always has somewhere to fall back to without the caller naming
    one. Each provider names its own fallback (see providers.py) so this
    stays in sync with _PROVIDERS without a second table to maintain."""
    other = primary.fallback
    if other is None:
        return None
    try:
        return get_provider(other)
    except ValueError:
        return None


def _complete_with_fallback(
    primary: LLMProvider, secondary: LLMProvider | None, system: str, user: str
) -> str | None:
    """Try `primary`, then `secondary` once on LLMUnavailable. None means
    both are down (or there was no secondary to try)."""
    try:
        return primary.complete(system, user)
    except LLMUnavailable:
        pass

    if secondary is None:
        return None

    try:
        return secondary.complete(system, user)
    except LLMUnavailable:
        return None


def _try_parse(raw: str) -> tuple[Proposal | None, str | None]:
    """Parse and validate one model response.

    Returns (Proposal, None) on success, or (None, error) describing why it
    failed — either malformed JSON or a schema violation.
    """
    text = raw.strip()
    if text.startswith("```"):
        # The prompt forbids markdown fences; tolerate one anyway rather
        # than spending a repair retry on a purely cosmetic mistake.
        text = text.strip("`")
        if text.startswith("json"):
            text = text[len("json") :]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"

    try:
        return Proposal.model_validate(data), None
    except ValidationError as exc:
        return None, str(exc)


class DiagnosisFailed(RuntimeError):
    """The model never produced a schema-valid proposal. Escalate the case."""
