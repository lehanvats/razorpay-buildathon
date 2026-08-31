"""SEND_PAYMENT_LINK — customer-authenticated payment.

The compliant path for amounts above the AFA threshold (Rs 15,000) and the
default for DROPOFF cases. A payment link does not consume an NPCI retry:
the customer authenticates it themselves, so it is not an auto-debit.

Closing the loop: when the customer pays, `payment_link.paid` arrives at the
webhook route and services/case_manager.py writes the outcome.
"""

from typing import Any

from app.executors.base import ExecutionResult
from app.schemas.proposal import ActionKind, Verdict


class PaymentLinkExecutor:
    """Creates a Razorpay Payment Link, optionally discounted."""

    kind = ActionKind.SEND_PAYMENT_LINK

    def execute(self, session: Any, case_id: str, verdict: Verdict) -> ExecutionResult:
        """Create the link and store its id on the action row.

        If `verdict.effective_discount_percent` is set, the link is for the
        reduced amount — the gate has already clamped it to <= 10% and
        confirmed no earlier discount was given on this case.

        Link expiry should match the discount expiry (48h) so a stale link
        cannot be paid at a price we no longer offer.
        """
        raise NotImplementedError("step-06: payment link executor")
