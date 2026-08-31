"""Failure taxonomy — maps Razorpay error metadata onto the four classes that
drive every downstream decision.

Deliberately a pure function over webhook payload fields: no DB, no network.
The class it returns selects which policy rules apply, the retry timing
strategy, and the copy the LLM is allowed to draft.

    HARD_DECLINE    stolen/blocked card, revoked mandate. Unrecoverable by
                    design — never spend an attempt, never message. Escalate.
    SOFT_FUNDS      insufficient balance. A *timing* problem: the money may
                    exist on the 1st of the month. Salary-window scheduling.
    SOFT_TECHNICAL  bank or gateway timeout / downtime. A *routing and
                    patience* problem: wait out the degraded bank.
    DROPOFF         customer abandoned checkout. A *persuasion* problem:
                    payment link + dunning, never an auto-charge.

Grounding: Razorpay surfaces `error_code`, `error_source`, `error_step` and
`error_reason` on payment.failed. NPCI/NACH bounce data shows insufficient
funds dominates mandate failures, which is why SOFT_FUNDS earns its own class
rather than living under a generic "soft decline".
"""

from enum import Enum


class FailureClass(str, Enum):
    """The four buckets. Stored on `cases.failure_class`."""

    HARD_DECLINE = "HARD_DECLINE"
    SOFT_FUNDS = "SOFT_FUNDS"
    SOFT_TECHNICAL = "SOFT_TECHNICAL"
    DROPOFF = "DROPOFF"


# Razorpay error_reason fragments -> FailureClass.
# Kept as data rather than branches so the mapping is reviewable by a
# non-Python reader and testable row by row.
#
# Anything unmatched MUST fall through to SOFT_TECHNICAL, never to
# HARD_DECLINE — misclassifying a recoverable failure as hard silently loses
# revenue, whereas the reverse only costs one retry that the attempt budget
# already caps. Not exhaustive against Razorpay's full published list; widen
# this table against real `error_reason` values as the step-08 seeder and
# live test-mode traffic surface them.
_REASON_MAP: dict[str, FailureClass] = {
    # Unrecoverable by design — never spend an attempt, never message.
    "card_stolen_or_lost": FailureClass.HARD_DECLINE,
    "mandate_revoked": FailureClass.HARD_DECLINE,
    "payment_frequency_limit_exceeded": FailureClass.HARD_DECLINE,
    "restricted_card": FailureClass.HARD_DECLINE,
    "invalid_card": FailureClass.HARD_DECLINE,
    "expired_card": FailureClass.HARD_DECLINE,
    "card_blacklisted": FailureClass.HARD_DECLINE,
    "fraudulent": FailureClass.HARD_DECLINE,
    # Insufficient balance — a timing problem, salary-window scheduling.
    "insufficient_funds": FailureClass.SOFT_FUNDS,
    # Bank/gateway timeout or downtime — wait out the degraded rail.
    "gateway_technical_error": FailureClass.SOFT_TECHNICAL,
    "bank_not_responding": FailureClass.SOFT_TECHNICAL,
    "issuer_unavailable": FailureClass.SOFT_TECHNICAL,
    "issuer_down": FailureClass.SOFT_TECHNICAL,
    "issuer_timeout": FailureClass.SOFT_TECHNICAL,
    "internal_error": FailureClass.SOFT_TECHNICAL,
    "server_error": FailureClass.SOFT_TECHNICAL,
    "gateway_error": FailureClass.SOFT_TECHNICAL,
    # Customer abandoned the flow — a persuasion problem, never an auto-charge.
    "payment_timed_out": FailureClass.DROPOFF,
    "payment_cancelled": FailureClass.DROPOFF,
    "otp_timeout": FailureClass.DROPOFF,
    "authentication_failed": FailureClass.DROPOFF,
}

#: Classes on which no charge attempt may ever be made. Consumed by
#: policy.rules.hard_decline_block — duplicated nowhere else.
UNRECOVERABLE: frozenset[FailureClass] = frozenset({FailureClass.HARD_DECLINE})


def classify(payment_entity: dict) -> FailureClass:
    """Classify one failed Razorpay payment entity.

    Args:
        payment_entity: the `payload.payment.entity` object from a
            `payment.failed` webhook.

    Returns:
        The FailureClass the case is opened with.

    The return value is written once at case creation and never recomputed:
    a case's class is part of its audit record, so if this mapping later
    changes, historical cases keep the class they were actually acted on
    under.
    """
    reason = (payment_entity.get("error_reason") or "").strip().lower()
    return _REASON_MAP.get(reason, FailureClass.SOFT_TECHNICAL)
