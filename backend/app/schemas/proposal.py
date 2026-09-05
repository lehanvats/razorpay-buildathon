"""The LLM contract — and the gate's output.

The model returns structured JSON only. Free-form output is rejected and
retried once, then the case escalates; a model that cannot fill this schema
does not get to act. Pydantic is doing the job Zod does in the TypeScript
blueprint: it is the enforcement boundary, not documentation.

Note what is NOT in the proposal: no amount, no recipient, no API call, no
raw SQL. The LLM chooses *timing, channel and tone* from a fixed action menu.
What it is allowed to do at all is the gate's decision, never the model's.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ActionKind(StrEnum):
    """The fixed action menu presented to the model. The model may return
    nothing outside this set — adding a member here is a product decision
    that also needs a policy rule and an executor."""

    SCHEDULE_RETRY = "SCHEDULE_RETRY"
    SEND_PAYMENT_LINK = "SEND_PAYMENT_LINK"
    OFFER_DISCOUNT = "OFFER_DISCOUNT"
    ESCALATE = "ESCALATE"


class Channel(StrEnum):
    EMAIL = "email"


class Proposal(BaseModel):
    """One structured suggestion from the LLM. Validated on arrival, stored
    verbatim in the audit trail whether or not it is approved — including
    proposals the gate blocks, which are the interesting ones."""

    action: ActionKind
    timing: datetime | None = Field(
        default=None,
        description="When to act, IST-aware. Required for SCHEDULE_RETRY. "
        "The gate may rewrite this (salary window, 24h pre-debit notice).",
    )
    channel: Channel | None = Field(
        default=None,
        description="Outreach channel; null for pure charge retries.",
    )
    discount_percent: int | None = Field(
        default=None,
        description="Requested discount, as a percent. Only meaningful for "
        "OFFER_DISCOUNT. The gate clamps this to "
        "policy.rules.MAX_DISCOUNT_PERCENT rather than blocking it outright.",
    )
    message_draft: str | None = Field(
        default=None,
        description="Customer-facing copy drafted by the model. Never sent "
        "unless the verdict approves an outreach action.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Below policy.rules.MIN_CONFIDENCE the stopping rule "
        "escalates instead of acting.",
    )
    reasoning: str = Field(
        description="One paragraph, stored verbatim in the audit trail and "
        "rendered on the case timeline. This is the explainability story — "
        "it is shown to judges, so it must survive round-tripping unedited.",
    )


class Decision(StrEnum):
    """What the gate concluded."""

    APPROVE = "APPROVE"
    """Proposal is compliant as-is; execute it unchanged."""

    REWRITE = "REWRITE"
    """Proposal is permissible but constrained — timing moved into the salary
    window, retry downgraded to an authenticated payment link, discount
    clamped to 10%. `effective_action` carries the amended action."""

    BLOCK = "BLOCK"
    """Not permitted. No action is taken; the case records the rule_id."""

    ESCALATE = "ESCALATE"
    """Hand to the human queue. The agent then goes silent on this case."""


class Verdict(BaseModel):
    """The gate's output — and the only thing an executor will accept.

    Executors take a Verdict, never a Proposal. That type distinction is how
    the "LLM proposes, policy disposes" invariant is enforced at the call
    site rather than by convention.
    """

    decision: Decision
    rule_id: str = Field(
        description="Which rule produced this verdict; 'PASS' if the proposal "
        "survived the whole chain untouched. Always populated, including on "
        "approval, so every action in the audit trail names its authority.",
    )
    effective_action: ActionKind | None = Field(
        default=None,
        description="The action to actually perform. Equals proposal.action "
        "for APPROVE, may differ for REWRITE, null for BLOCK/ESCALATE.",
    )
    effective_timing: datetime | None = None
    effective_discount_percent: int | None = None
    explanation: str = Field(
        description="Human-readable reason, shown on the case timeline next to the rule_id badge.",
    )
    message_draft: str | None = Field(
        default=None,
        description="Normally carried through from the proposal verbatim -- "
        "rules don't rewrite the model's customer-facing copy. The one "
        "exception is a rule that rewrites the action itself into an "
        "outreach action the original proposal never needed a message for "
        "(e.g. AFA_THRESHOLD_EXCEEDED downgrading a bare retry to a payment "
        "link); such a rule may supply a safe fallback here so the verdict "
        "it hands to DunningExecutor is actually sendable. Executors take "
        "only a Verdict, never the original Proposal, so this field is how "
        "DunningExecutor and PreDebitNoticeExecutor reach the drafted text.",
    )
    channel: Channel | None = Field(
        default=None,
        description="Carried through from the proposal verbatim, or filled "
        "in by the same rewriting rule, for the same reason as message_draft.",
    )
