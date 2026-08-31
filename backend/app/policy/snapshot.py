"""The gate's input contract.

`CaseSnapshot` is a flat, plain-data view of everything the policy rules are
allowed to consider. It exists so that `gate()` can stay pure: no session, no
lazy-loaded ORM relationships, no clock reads hidden inside a rule.

If a new rule needs a new fact, add an explicit field here and populate it at
the call site. That is the point — the set of inputs the policy depends on is
readable in one screen, and every rule test can construct one by hand without
a database.
"""

from dataclasses import dataclass
from datetime import datetime

from app.core.holdout import Arm
from app.core.taxonomy import FailureClass


@dataclass(frozen=True)
class CaseSnapshot:
    """Immutable view of a case at the moment a proposal is evaluated."""

    case_id: str
    amount_paise: int
    """Amount in paise (Razorpay's unit). ₹15,000 == 1_500_000 paise —
    integer money only, never float."""

    method: str
    """Razorpay payment method: card | upi | netbanking | emandate | ..."""

    failure_class: FailureClass
    arm: Arm

    attempts_used: int
    """Charge attempts already spent on this case, original included.
    NPCI caps AutoPay at 1 original + 3 retries."""

    is_mandate: bool
    """True for subscription / e-mandate / UPI AutoPay debits. Gates the
    RBI 24-hour pre-debit notification rule."""

    pre_debit_notice_sent_at: datetime | None
    """When the customer was notified of an upcoming mandate debit. The RBI
    e-mandate framework requires >= 24h between this and the debit."""

    messages_sent: int
    """Outreach messages sent so far. Capped at 3 per case."""

    last_contact_at: datetime | None
    """Timestamp of the most recent outreach; enforces the 24h cooldown."""

    discount_already_offered: bool
    """A discount may be offered at most once per case."""

    now: datetime
    """Evaluation time, passed in rather than read from the clock, so rule
    tests are deterministic and the audit record can be replayed."""
