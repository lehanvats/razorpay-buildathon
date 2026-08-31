"""Case lifecycle — where the loop is actually wired together.

This is the one module that knows the whole sequence, so the ordering
constraints that matter live here rather than being spread across routes.

The recovery loop:

    webhook -> open case -> assign arm -> classify
                              |
                     control -+-> observe only, no action, EVER
                              |
                   treatment -+-> diagnose (LLM proposes)
                                    -> gate (policy disposes)
                                        -> approve  -> schedule/execute
                                        -> rewrite  -> schedule amended action
                                        -> block    -> log rule_id, stop
                                        -> escalate -> human queue
                              |
    later webhook (paid) ------+-> write outcome  <-- BOTH arms
"""

from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.core.holdout import Arm, assign_arm
from app.core.taxonomy import classify
from app.db.models import Case


def _is_mandate(payment_entity: dict) -> bool:
    """True for subscription / e-mandate / UPI AutoPay debits.

    Razorpay attaches `subscription_id` to a payment driven by a mandate; a
    one-off checkout payment never carries it.
    """
    return payment_entity.get("subscription_id") is not None


def handle_payment_failed(session: Any, event: dict) -> str:
    """Open a case from a `payment.failed` event and drive the first step.

    Order is load-bearing:
      1. Persist the raw webhook (dedupe on event id) — before anything else,
         so a crash mid-processing is replayable. Done by the caller
         (api/routes/webhooks.py) before this function runs.
      2. Create the case row.
      3. Assign the arm (core.holdout).
      4. Classify (core.taxonomy).
      5. Only now branch on arm.

    Steps 3-4 happen for control cases too: a control case is *observed*, not
    ignored, and its class is needed to compute per-class control rates.

    Dedupes on `razorpay_order_id`: Razorpay allows several payment attempts
    against one Order, so a repeat `payment.failed` for an order that already
    has a case returns the existing case id rather than opening a second one.
    The case's class and arm were written once and are not recomputed.

    Returns:
        The case id — new, or the existing one for a repeat failure.
    """
    entity = event["payload"]["payment"]["entity"]
    order_id = entity["order_id"]

    existing = session.execute(
        select(Case).where(Case.razorpay_order_id == order_id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id

    case_id = str(uuid4())
    arm = assign_arm(case_id)
    # TODO(step-07): audit.record(session, case_id=case_id, actor=Actor.WEBHOOK,
    #   event_type=EventType.CASE_OPENED, payload={"order_id": order_id})
    # TODO(step-07): audit.record(session, case_id=case_id, actor=Actor.POLICY,
    #   event_type=EventType.ARM_ASSIGNED, payload={"arm": arm.value})

    failure_class = classify(entity)
    # TODO(step-07): audit.record(session, case_id=case_id, actor=Actor.POLICY,
    #   event_type=EventType.CLASSIFIED, payload={"failure_class": failure_class.value})

    case = Case(
        id=case_id,
        razorpay_order_id=order_id,
        razorpay_payment_id=entity["id"],
        customer_email=entity.get("email"),
        amount_paise=entity["amount"],
        currency=entity.get("currency", "INR"),
        method=entity.get("method", "unknown"),
        is_mandate=_is_mandate(entity),
        failure_class=failure_class.value,
        failure_reason_raw=entity.get("error_reason"),
        arm=arm.value,
        status="control_observed" if arm is Arm.CONTROL else "open",
        attempts_used=1,
        messages_sent=0,
        discount_offered=False,
    )
    session.add(case)
    session.flush()

    # TODO(step-04): if is_actionable(arm): advance_case(session, case_id)

    return case_id


def advance_case(session: Any, case_id: str) -> None:
    """Run one diagnose -> gate -> act cycle for a treated case.

    Called on case creation and again after any scheduled action completes
    without recovering. Re-entrant and safe to call twice: it no-ops on cases
    that are recovered, escalated or exhausted.

    Refuses to run on control cases — asserts rather than silently returning,
    because a control case reaching this function means the branch above is
    broken and silence would corrupt the headline metric.
    """
    raise NotImplementedError("step-04: agent step orchestration")


def handle_payment_succeeded(session: Any, event: dict) -> None:
    """Close the loop on `payment.captured` / `order.paid` / `payment_link.paid`.

    CRITICAL: this path must NOT short-circuit on `arm == control`.

    Control cases recover on their own — that self-recovery rate is exactly
    what the treatment is measured against. Skipping the outcome write for
    control cases would read as a 0% control rate and make the incremental
    number a lie in our own favour. The holdout gates *actions*, never
    *measurement*.

    Also cancels any pending scheduled action for the case: charging a
    customer who has already paid is the worst bug this system could ship.
    """
    raise NotImplementedError("step-03: outcome recording")


def escalate(session: Any, case_id: str, *, rule_id: str, reason: str) -> None:
    """Move a case to the human queue and silence the agent on it.

    After escalation no further automated action is taken. Silence is the
    correct behaviour under the stopping rule, not a stalled case.
    """
    raise NotImplementedError("step-05: escalation")


def get_timeline(session: Any, case_id: str) -> list[dict]:
    """Read the append-only audit trail for the case-detail view."""
    raise NotImplementedError("step-07: timeline rendering")
