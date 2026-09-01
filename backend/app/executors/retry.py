"""SCHEDULE_RETRY — create a fresh charge attempt.

Consumes one unit of the NPCI attempt budget, so this executor must never run
without an approving verdict; policy.rules.attempt_budget is what stands
between us and a compliance breach.

Razorpay has no "retry this payment" call — a retry is a *new Order* against
the same customer, which is why `actions.razorpay_ref` stores a new order id
and the recovery is later matched back through the `order.paid` webhook.
"""

from typing import Any

from app.db.models import Case
from app.executors.base import ExecutionResult, with_audit
from app.integrations.razorpay_client import create_order
from app.schemas.proposal import ActionKind, Verdict


class RetryExecutor:
    """Creates a new Razorpay Order for the case's amount."""

    kind = ActionKind.SCHEDULE_RETRY

    @with_audit
    def execute(self, session: Any, case_id: str, verdict: Verdict) -> ExecutionResult:
        """Create the order, increment `cases.attempts_used`, record the ref.

        Order of operations matters: increment the attempt counter in the same
        transaction as the order creation. Crashing after charging but before
        counting would let the case exceed the NPCI cap on the next pass.
        """
        case = session.get(Case, case_id)
        if case is None:
            return ExecutionResult(ok=False, error=f"case {case_id} not found")

        try:
            order = create_order(case.amount_paise, case.currency, case_id=case.id)
        except Exception as exc:  # noqa: BLE001 — reported, not raised; see base.Executor.execute
            return ExecutionResult(ok=False, error=str(exc))

        case.attempts_used += 1
        session.flush()

        return ExecutionResult(ok=True, razorpay_ref=order.get("id"))
