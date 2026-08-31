"""The policy gate — the single path from proposal to money action.

The design invariant the whole system hangs on:

    The LLM can only propose. The gate is the sole path to any money action.

Nothing in this module imports from `app.db`, `app.integrations`, or any
executor. It is a pure function of (CaseSnapshot, Proposal). That purity is
what makes tests/test_policy_gate.py writable without a database, and it is
what lets the audit trail claim that a blocked proposal was blocked by a
named, reviewable rule rather than by a model's mood.

Callers must treat the verdict as authoritative: executors take a Verdict,
never a Proposal.
"""

from app.policy.rules import RULE_CHAIN
from app.policy.snapshot import CaseSnapshot
from app.schemas.proposal import Proposal, Verdict


def gate(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict:
    """Evaluate an LLM proposal against the rulebook.

    Walks RULE_CHAIN in order. The first rule that returns a blocking verdict
    wins and evaluation stops. Rewriting rules (AFA, pre-debit notice, salary
    window, discount clamp) apply in sequence, each seeing the previous
    rewrite, so the final verdict reflects every applicable constraint.

    Args:
        snapshot: plain-data view of the case; see policy/snapshot.py.
        proposal: the LLM's structured, schema-validated suggestion.

    Returns:
        A Verdict carrying decision (APPROVE | REWRITE | BLOCK | ESCALATE),
        the rule_id responsible, and — for APPROVE/REWRITE — the effective
        action the executor should perform.

    Guarantees the caller may rely on:
      * A verdict always names a rule_id, including on approval (which rule
        last touched it, or PASS if the proposal survived untouched).
      * Never raises for a well-formed proposal; an unrepresentable
        combination returns ESCALATE rather than blowing up a webhook.
      * Same inputs, same output — no clock reads, no randomness. Time enters
        only via `snapshot.now`.
    """
    raise NotImplementedError("step-05: policy engine and compliance gate")
