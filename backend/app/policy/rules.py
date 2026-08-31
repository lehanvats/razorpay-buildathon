"""The rulebook.

Eight deterministic rules. Each takes (snapshot, proposal) and returns either
None (this rule has no opinion) or a Verdict that blocks or rewrites the
proposal. No LLM, no I/O, no randomness — every rule is a testable line item,
and a blocked proposal is always logged with the rule_id that blocked it.

This table is the "explainable, bounded, gated" story and is reproduced
verbatim in the README and the pitch deck:

  Rule              Trigger                    Effect                                          Grounded in
  ----------------  -------------------------  ----------------------------------------------  -------------------------
  Hard-decline      failure_class=HARD_DECLINE Never retry, never message; escalate            Card-network rules
  Attempt budget    any charge attempt         <= 1 original + 3 retries, then stop            NPCI AutoPay cap
  Pre-debit notice  mandate retry              customer notified >= 24h before debit           RBI e-mandate framework
  AFA threshold     amount > Rs 15,000         no auto-charge; authenticated link only         RBI e-mandate framework
  Salary window     SOFT_FUNDS                 retry into 1st-5th, or +72h, whichever nearer   NACH bounce pattern
  Contact cooldown  any outreach               >= 24h between messages, <= 3 per case          Anti-spam / brand safety
  Discount bound    OFFER_DISCOUNT             <= 10%, once per case, expires in 48h           Margin cap
  Stopping rule     budget spent or conf < 0.6 escalate to human queue; agent goes silent      Track 3: compliant escalation
"""

from datetime import timedelta

from app.policy.snapshot import CaseSnapshot
from app.schemas.proposal import Proposal, Verdict


class RuleId:
    """Stable identifiers. These strings appear in the audit trail, in the UI
    badge, and on screen during the demo — never rename one after it has been
    written to an audit event."""

    HARD_DECLINE_BLOCK = "HARD_DECLINE_BLOCK"
    ATTEMPT_BUDGET_EXHAUSTED = "ATTEMPT_BUDGET_EXHAUSTED"
    PRE_DEBIT_NOTICE_REQUIRED = "PRE_DEBIT_NOTICE_REQUIRED"
    AFA_THRESHOLD_EXCEEDED = "AFA_THRESHOLD_EXCEEDED"
    SALARY_WINDOW_RESCHEDULE = "SALARY_WINDOW_RESCHEDULE"
    CONTACT_COOLDOWN = "CONTACT_COOLDOWN"
    DISCOUNT_BOUND = "DISCOUNT_BOUND"
    LOW_CONFIDENCE_ESCALATE = "LOW_CONFIDENCE_ESCALATE"


# --- Regulatory and business constants -------------------------------------
# Each carries its source. Changing one is a compliance decision, not a tuning
# knob, so they live here rather than in config.

MAX_CHARGE_ATTEMPTS = 4
"""1 original debit + 3 retries. Source: NPCI AutoPay retry cap."""

PRE_DEBIT_NOTICE_HOURS = 24
"""Source: RBI e-mandate framework — customer must be notified 24h before
a recurring debit."""

AFA_THRESHOLD_PAISE = 1_500_000
"""Rs 15,000. Above this an e-mandate debit requires Additional Factor of
Authentication, so no auto-charge is permitted — only a customer-authenticated
payment link. Source: RBI e-mandate framework."""

SALARY_WINDOW_DAYS = (1, 2, 3, 4, 5)
"""Retries for insufficient-funds failures are steered into the start of the
month. Source: NACH bounce data — insufficient funds is a salary-cycle
problem, not a willingness problem."""

SOFT_FUNDS_FALLBACK = timedelta(hours=72)
"""If the next salary window is further away than this, retry sooner."""

CONTACT_COOLDOWN_HOURS = 24
MAX_MESSAGES_PER_CASE = 3
MAX_DISCOUNT_PERCENT = 10
DISCOUNT_EXPIRY = timedelta(hours=48)
MIN_CONFIDENCE = 0.6
"""Below this the agent does not act; it escalates and goes silent."""


# --- Rules -----------------------------------------------------------------
# Signature is uniform so gate() can run them in order:
#     (snapshot, proposal) -> Verdict | None
# Returning None means "no opinion, continue to the next rule".


def hard_decline_block(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """Unrecoverable failures never consume an attempt or a message.

    This is the rule the demo shows firing: the LLM is deliberately prompted
    loosely, proposes a retry on a HARD_DECLINE case, and this blocks it with
    rule_id HARD_DECLINE_BLOCK. One failure handled gracefully, with receipt.
    """
    raise NotImplementedError("step-05: policy engine")


def attempt_budget(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """Cap charge attempts at MAX_CHARGE_ATTEMPTS, then stop permanently.

    Only charge-type actions count against the budget; sending a payment link
    the customer authenticates themselves does not consume an NPCI retry.
    """
    raise NotImplementedError("step-05: policy engine")


def pre_debit_notice(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """Mandate debits require >= 24h notice.

    If no notice has been sent, this does not block outright — it rewrites the
    action to send the notice first and re-schedules the debit for
    notice_time + 24h. That rewrite is why the gate returns a Verdict rather
    than a bool.
    """
    raise NotImplementedError("step-05: policy engine")


def afa_threshold(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """Above Rs 15,000 no auto-charge is permitted.

    Rewrites SCHEDULE_RETRY to SEND_PAYMENT_LINK so the customer authenticates
    the payment themselves.
    """
    raise NotImplementedError("step-05: policy engine")


def salary_window(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """Steer SOFT_FUNDS retries into the 1st-5th of the month.

    Effective timing is min(next salary window, now + 72h) — never later than
    the fallback, so a case failing on the 6th does not wait 26 days.
    """
    raise NotImplementedError("step-05: policy engine")


def contact_cooldown(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """At most 3 messages per case, at least 24h apart."""
    raise NotImplementedError("step-05: policy engine")


def discount_bound(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """Discounts are bounded money actions: <= 10%, once, expiring in 48h.

    An over-large discount is clamped rather than blocked; a second discount
    on the same case is blocked.
    """
    raise NotImplementedError("step-05: policy engine")


def stopping_rule(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """Escalate to the human queue when the agent should stop.

    Fires on exhausted budget or confidence < 0.6. After escalation the agent
    takes no further action on the case — silence is the correct behaviour,
    not a bug.
    """
    raise NotImplementedError("step-05: policy engine")


#: Evaluation order. Blocking rules run before rewriting rules so a case that
#: must not be touched is never rewritten into a different action first.
#: gate() walks this list; the ordering is part of the policy and is asserted
#: in tests.
RULE_CHAIN = (
    hard_decline_block,
    stopping_rule,
    attempt_budget,
    afa_threshold,
    pre_debit_notice,
    contact_cooldown,
    discount_bound,
    salary_window,
)
