"""SEND_PAYMENT_LINK — customer-authenticated payment.

The compliant path for amounts above the AFA threshold (Rs 15,000) and the
default for DROPOFF cases. A payment link does not consume an NPCI retry:
the customer authenticates it themselves, so it is not an auto-debit.

Closing the loop: when the customer pays, `payment_link.paid` arrives at the
webhook route and services/case_manager.py writes the outcome — via the
`reference_id` fallback lookup, since the link is its own new Order (see
integrations/razorpay_client.create_payment_link).
"""

from typing import Any

from app.db.models import Case
from app.executors.base import ExecutionResult, with_audit
from app.integrations.razorpay_client import create_payment_link
from app.schemas.proposal import ActionKind, Verdict


class PaymentLinkExecutor:
    """Creates a Razorpay Payment Link, optionally discounted."""

    kind = ActionKind.SEND_PAYMENT_LINK

    @with_audit
    def execute(self, session: Any, case_id: str, verdict: Verdict) -> ExecutionResult:
        """Create the link and store its id on the action row.

        If `verdict.effective_discount_percent` is set, the link is for the
        reduced amount — the gate has already clamped it to <= 10% and
        confirmed no earlier discount was given on this case.

        Link expiry defaults to match the discount expiry (48h, see
        integrations.razorpay_client.create_payment_link) so a stale link
        cannot be paid at a price we no longer offer.
        """
        case = session.get(Case, case_id)
        if case is None:
            return ExecutionResult(ok=False, error=f"case {case_id} not found")
        if not case.customer_email:
            return ExecutionResult(ok=False, error="no customer email on file")

        amount_paise = case.amount_paise
        discount_percent = verdict.effective_discount_percent
        if discount_percent:
            amount_paise -= amount_paise * discount_percent // 100

        try:
            link = create_payment_link(amount_paise, case.customer_email, case_id=case.id)
        except Exception as exc:  # noqa: BLE001 — reported, not raised; see base.Executor.execute
            return ExecutionResult(ok=False, error=str(exc))

        if discount_percent:
            case.discount_offered = True
            session.flush()

        return ExecutionResult(ok=True, razorpay_ref=link.get("id"), detail=link.get("short_url"))
