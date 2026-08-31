"""Diagnosis — the LLM proposes, structurally.

Runs for treated cases only. Control cases never reach this module; that
check belongs upstream in services/case_manager.py so there is exactly one
place where the holdout is honoured.

The output of this module is a Proposal, which is *not* an instruction. It
goes to policy.gate.gate() and nowhere else. This module must not import any
executor.
"""

from app.schemas.proposal import Proposal

MAX_PARSE_RETRIES = 1
"""Free-form or schema-invalid output is retried exactly once with a
repair instruction, then the case escalates. A model that cannot fill the
schema twice does not get a third chance to improvise."""


def diagnose(case_context: dict, *, loose_prompt: bool = False) -> Proposal:
    """Ask the model for a structured proposal.

    Flow:
      1. Build system + user prompts (agent/prompts.py).
      2. Call the configured provider; on LLMUnavailable, fall back once to
         the secondary provider.
      3. Parse JSON and validate against Proposal. On failure, retry once
         with the validation error fed back, then raise DiagnosisFailed.
      4. Write an LLM_PROPOSED audit event carrying `reasoning` verbatim
         (or LLM_REJECTED on give-up) before returning.

    Args:
        case_context: flat dict of case facts; see prompts.build_case_prompt.
        loose_prompt: use the deliberately under-constrained demo prompt so
            the gate can be seen blocking a hard-decline retry. Never true in
            normal operation.

    Returns:
        A validated Proposal. Caller must pass it to the policy gate.

    Raises:
        DiagnosisFailed: model could not produce valid structured output.
            Caller escalates the case — it does not act on a guess.
    """
    raise NotImplementedError("step-04: diagnosis")


class DiagnosisFailed(RuntimeError):
    """The model never produced a schema-valid proposal. Escalate the case."""
