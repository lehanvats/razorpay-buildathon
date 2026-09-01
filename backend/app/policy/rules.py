"""The rulebook.

Eight deterministic rules. Each takes (snapshot, proposal) and returns either
None (this rule has no opinion) or a Verdict that blocks or rewrites the
proposal. No LLM, no I/O, no randomness — every rule is a testable line item,
and a blocked proposal is always logged with the rule_id that blocked it.

This table is the "explainable, bounded, gated" story and is reproduced
verbatim in the README and the pitch deck:

  Rule               Trigger              Effect                               Grounded in
  ------------------ -------------------- ------------------------------------ ---------------------
  Hard-decline       HARD_DECLINE         Never retry/message; escalate        Card network
  Attempt budget     any charge attempt   <=1 original + 3 retries; stop       NPCI cap
  Pre-debit notice   mandate retry        notice >=24h before debit            RBI mandate
  AFA threshold      amount > Rs 15,000   no auto-charge; use payment link     RBI mandate
  Salary window      SOFT_FUNDS           retry 1st-5th, else +72h             NACH pattern
  Contact cooldown   any outreach         >=24h between msgs, <=3/case         Anti-spam
  Discount bound     OFFER_DISCOUNT       <=10%, once/case, 48h expiry         Margin cap
  Stopping rule      budget/confidence    escalate; agent goes silent          Compliant escalation
"""

from datetime import timedelta

from app.core.taxonomy import FailureClass
from app.policy.snapshot import CaseSnapshot
from app.schemas.proposal import ActionKind, Decision, Proposal, Verdict


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

#: Actions that spend an NPCI charge attempt. A payment link is customer-
#: authenticated, not an auto-debit, so it is not in this set.
_CHARGE_ACTIONS = frozenset({ActionKind.SCHEDULE_RETRY})

#: Actions that message the customer, and so are subject to the contact
#: cooldown. A bare charge retry has no channel/message_draft.
_OUTREACH_ACTIONS = frozenset({ActionKind.SEND_PAYMENT_LINK, ActionKind.OFFER_DISCOUNT})


# --- Rules -----------------------------------------------------------------
# Signature is uniform so gate() can run them in order:
#     (snapshot, proposal) -> Verdict | None
# Returning None means "no opinion, continue to the next rule".
#
# A REWRITE verdict only sets the fields it actually wants to change
# (effective_action / effective_timing / effective_discount_percent); gate()
# threads those forward onto the next rule's input and leaves anything a
# rule didn't touch as-is. Setting a field a rule doesn't own would clobber
# an earlier rewrite when gate() merges verdicts in chain order.


def hard_decline_block(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """Unrecoverable failures never consume an attempt or a message.

    This is the rule the demo shows firing: the LLM is deliberately prompted
    loosely, proposes a retry on a HARD_DECLINE case, and this blocks it with
    rule_id HARD_DECLINE_BLOCK. One failure handled gracefully, with receipt.
    """
    if snapshot.failure_class is not FailureClass.HARD_DECLINE:
        return None
    return Verdict(
        decision=Decision.BLOCK,
        rule_id=RuleId.HARD_DECLINE_BLOCK,
        explanation="Hard decline is unrecoverable by design — no charge "
        "retry and no outreach message is permitted.",
    )


def stopping_rule(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """Escalate to the human queue when the model itself is unsure.

    confidence < MIN_CONFIDENCE escalates rather than acting on a guess —
    that is a correct, desirable outcome, not a failure. (The other stopping
    condition, an exhausted attempt budget, is handled by attempt_budget
    below, later in the chain — kept as a separate rule/rule_id since it is
    a distinct, independently testable trigger.)
    """
    if proposal.confidence >= MIN_CONFIDENCE:
        return None
    return Verdict(
        decision=Decision.ESCALATE,
        rule_id=RuleId.LOW_CONFIDENCE_ESCALATE,
        explanation=f"Confidence {proposal.confidence:.2f} is below the "
        f"{MIN_CONFIDENCE} threshold; escalating to human review rather "
        "than acting on a guess.",
    )


def attempt_budget(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """Cap charge attempts at MAX_CHARGE_ATTEMPTS, then stop permanently.

    Only charge-type actions count against the budget; sending a payment link
    the customer authenticates themselves does not consume an NPCI retry.
    """
    if proposal.action not in _CHARGE_ACTIONS:
        return None
    if snapshot.attempts_used < MAX_CHARGE_ATTEMPTS:
        return None
    return Verdict(
        decision=Decision.BLOCK,
        rule_id=RuleId.ATTEMPT_BUDGET_EXHAUSTED,
        explanation=f"{snapshot.attempts_used} charge attempts already used; "
        f"NPCI caps AutoPay at {MAX_CHARGE_ATTEMPTS} (1 original + 3 "
        "retries).",
    )


def afa_threshold(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """Above Rs 15,000 no auto-charge is permitted.

    Rewrites SCHEDULE_RETRY to SEND_PAYMENT_LINK so the customer authenticates
    the payment themselves.
    """
    if proposal.action is not ActionKind.SCHEDULE_RETRY:
        return None
    if snapshot.amount_paise <= AFA_THRESHOLD_PAISE:
        return None
    return Verdict(
        decision=Decision.REWRITE,
        rule_id=RuleId.AFA_THRESHOLD_EXCEEDED,
        effective_action=ActionKind.SEND_PAYMENT_LINK,
        explanation=f"Amount {snapshot.amount_paise}p exceeds the Rs 15,000 "
        "AFA threshold; auto-charge is not permitted, rewriting to a "
        "customer-authenticated payment link.",
    )


def pre_debit_notice(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """Mandate debits require >= 24h notice.

    If no notice has been sent, this does not block outright — it rewrites the
    action to send the notice first and re-schedules the debit for
    notice_time + 24h. That rewrite is why the gate returns a Verdict rather
    than a bool.
    """
    if not snapshot.is_mandate or proposal.action is not ActionKind.SCHEDULE_RETRY:
        return None

    notice_sent_at = snapshot.pre_debit_notice_sent_at
    notice_window = timedelta(hours=PRE_DEBIT_NOTICE_HOURS)

    if notice_sent_at is not None and snapshot.now - notice_sent_at >= notice_window:
        return None  # notice has matured; nothing to rewrite

    if notice_sent_at is None:
        effective_timing = snapshot.now + notice_window
        explanation = (
            "No pre-debit notice sent yet; scheduling the notice now and "
            "deferring the debit to notice + 24h, per the RBI e-mandate "
            "framework."
        )
    else:
        effective_timing = notice_sent_at + notice_window
        explanation = (
            f"Pre-debit notice sent at {notice_sent_at.isoformat()} has not "
            "yet matured 24h; deferring the debit to notice + 24h."
        )

    return Verdict(
        decision=Decision.REWRITE,
        rule_id=RuleId.PRE_DEBIT_NOTICE_REQUIRED,
        effective_timing=effective_timing,
        explanation=explanation,
    )


def contact_cooldown(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """At most 3 messages per case, at least 24h apart."""
    if proposal.action not in _OUTREACH_ACTIONS:
        return None

    if snapshot.messages_sent >= MAX_MESSAGES_PER_CASE:
        return Verdict(
            decision=Decision.BLOCK,
            rule_id=RuleId.CONTACT_COOLDOWN,
            explanation=f"{snapshot.messages_sent} messages already sent; "
            f"cap is {MAX_MESSAGES_PER_CASE} per case.",
        )

    cooldown = timedelta(hours=CONTACT_COOLDOWN_HOURS)
    if snapshot.last_contact_at is not None and snapshot.now - snapshot.last_contact_at < cooldown:
        return Verdict(
            decision=Decision.BLOCK,
            rule_id=RuleId.CONTACT_COOLDOWN,
            explanation=f"Last contact at {snapshot.last_contact_at.isoformat()} "
            f"is under {CONTACT_COOLDOWN_HOURS}h ago; blocking a second "
            "message.",
        )

    return None


def discount_bound(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """Discounts are bounded money actions: <= 10%, once, expiring in 48h.

    An over-large discount is clamped rather than blocked; a second discount
    on the same case is blocked.
    """
    if proposal.action is not ActionKind.OFFER_DISCOUNT:
        return None

    if snapshot.discount_already_offered:
        return Verdict(
            decision=Decision.BLOCK,
            rule_id=RuleId.DISCOUNT_BOUND,
            explanation="A discount has already been offered on this case; "
            "only one is permitted per case.",
        )

    requested = proposal.discount_percent
    if requested is None or requested <= MAX_DISCOUNT_PERCENT:
        return None

    return Verdict(
        decision=Decision.REWRITE,
        rule_id=RuleId.DISCOUNT_BOUND,
        effective_discount_percent=MAX_DISCOUNT_PERCENT,
        explanation=f"Requested {requested}% discount exceeds the "
        f"{MAX_DISCOUNT_PERCENT}% margin cap; clamped.",
    )


def salary_window(snapshot: CaseSnapshot, proposal: Proposal) -> Verdict | None:
    """Steer SOFT_FUNDS retries into the 1st-5th of the month.

    Effective timing is min(next salary window, now + 72h) — never later than
    the fallback, so a case failing on the 6th does not wait 26 days.
    """
    if snapshot.failure_class is not FailureClass.SOFT_FUNDS:
        return None
    if proposal.action is not ActionKind.SCHEDULE_RETRY:
        return None

    candidate = snapshot.now
    while candidate.day not in SALARY_WINDOW_DAYS:
        candidate += timedelta(days=1)
    next_window = candidate
    fallback = snapshot.now + SOFT_FUNDS_FALLBACK
    effective_timing = min(next_window, fallback)

    return Verdict(
        decision=Decision.REWRITE,
        rule_id=RuleId.SALARY_WINDOW_RESCHEDULE,
        effective_timing=effective_timing,
        explanation="SOFT_FUNDS retries are steered into the 1st-5th of the "
        f"month; rescheduled to {effective_timing.isoformat()} (salary "
        f"window or {SOFT_FUNDS_FALLBACK} fallback, whichever is nearer).",
    )


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
