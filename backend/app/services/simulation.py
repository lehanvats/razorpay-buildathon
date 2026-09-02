"""Customer-behaviour simulation for the demo batch.

Two properties this simulation must have or the headline number is
meaningless — see `scripts/simulate_customers.py`'s module docstring for the
full probability table and the reasoning behind each:

  1. Control cases self-recover too.
  2. Treatment effect comes from timing (the salary window), not a flat
     bonus applied because a case was treated.
"""

import random
from datetime import UTC, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.core.holdout import Arm
from app.core.taxonomy import FailureClass
from app.db.models import Action, Case
from app.policy.rules import SALARY_WINDOW_DAYS
from app.services.case_manager import handle_payment_succeeded

_IST_OFFSET = timedelta(hours=5, minutes=30)

#: class -> (control, treated_in_window, treated_off_window).
#: DROPOFF and HARD_DECLINE have no "in window" concept, so their third slot
#: is unused (see `_pay_probability`). Tune, then document the final numbers
#: used for a given demo run in the README.
PAYMENT_PROBABILITIES: dict[FailureClass, tuple[float, float, float]] = {
    FailureClass.SOFT_FUNDS: (0.15, 0.55, 0.20),
    FailureClass.SOFT_TECHNICAL: (0.25, 0.50, 0.35),
    FailureClass.DROPOFF: (0.20, 0.45, 0.45),
    FailureClass.HARD_DECLINE: (0.02, 0.02, 0.02),  # never treated in practice
}

#: Cases still awaiting a customer decision. Terminal statuses (recovered,
#: escalated, exhausted) are excluded — the loop is over, nothing to simulate.
_OPEN_STATUSES = ("open", "scheduled", "control_observed", "awaiting_customer")


def _scheduled_in_salary_window(session: Any, case_id: str) -> bool:
    """Whether this case's most recent SCHEDULE_RETRY action falls in the
    1st-5th (IST) salary window — the mechanism the treatment effect is
    supposed to model, not a flat bonus for having been treated at all."""
    action = session.execute(
        select(Action)
        .where(Action.case_id == case_id, Action.kind == "SCHEDULE_RETRY")
        .order_by(Action.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if action is None:
        return False
    ist_day = (action.scheduled_for.astimezone(UTC) + _IST_OFFSET).day
    return ist_day in SALARY_WINDOW_DAYS


def _pay_probability(session: Any, case: Case) -> float:
    failure_class = FailureClass(case.failure_class)
    control_p, in_window_p, off_window_p = PAYMENT_PROBABILITIES[failure_class]

    if case.arm != Arm.TREATMENT.value or failure_class is FailureClass.HARD_DECLINE:
        # Control never gets a treatment bonus; HARD_DECLINE is never
        # actioned regardless of arm, so it always reads its own baseline.
        return control_p
    if failure_class is FailureClass.SOFT_FUNDS:
        return in_window_p if _scheduled_in_salary_window(session, case.id) else off_window_p
    return in_window_p


def simulate_customers(session: Any, *, seed: int | None = None) -> dict[str, Any]:
    """Walk open cases and decide, per `PAYMENT_PROBABILITIES`, whether the
    customer pays — firing the corresponding success event through the same
    `handle_payment_succeeded` path a real `payment.captured` webhook would.

    Returns how many cases were considered and how many "paid".
    """
    rng = random.Random(seed)
    cases = session.execute(select(Case).where(Case.status.in_(_OPEN_STATUSES))).scalars().all()

    paid = 0
    for case in cases:
        if rng.random() >= _pay_probability(session, case):
            continue
        event = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "order_id": case.razorpay_order_id,
                        "id": f"pay_{uuid4().hex[:14]}",
                        "amount": case.amount_paise,
                        "currency": case.currency,
                    }
                }
            },
        }
        handle_payment_succeeded(session, event)
        paid += 1

    session.commit()
    return {"considered": len(cases), "paid": paid}
