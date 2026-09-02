"""Synthetic `payment.failed` payload generation for the demo batch.

Shared by `scripts/seed_failures.py` (posts real signed HTTP webhooks
against a running server — the real ingress path, proving the demo isn't a
shortcut) and `api/routes/demo.py`'s `POST /seed` (in-process, for the
"seed" button inside a live demo — see `seed_batch`'s docstring for why that
path skips the raw `webhook_events` row the script's HTTP path writes).
"""

import random
from collections import Counter
from typing import Any
from uuid import uuid4

from app.core.taxonomy import FailureClass
from app.db.models import Case
from app.services.case_manager import handle_payment_failed

#: Class mix, roughly reflecting the Indian market rather than uniform —
#: insufficient funds dominates mandate failures (NPCI/NACH bounce data),
#: technical declines cluster on specific banks. State this in the README.
FAILURE_CLASS_MIX: dict[FailureClass, float] = {
    FailureClass.SOFT_FUNDS: 0.35,
    FailureClass.SOFT_TECHNICAL: 0.30,
    FailureClass.DROPOFF: 0.20,
    FailureClass.HARD_DECLINE: 0.15,
}

#: One representative Razorpay `error_reason` per class — `taxonomy.classify`
#: reads this back through `_REASON_MAP`, so a seeded case lands in the class
#: it was generated for.
_ERROR_REASON_BY_CLASS: dict[FailureClass, str] = {
    FailureClass.HARD_DECLINE: "card_stolen_or_lost",
    FailureClass.SOFT_FUNDS: "insufficient_funds",
    FailureClass.SOFT_TECHNICAL: "gateway_technical_error",
    FailureClass.DROPOFF: "payment_timed_out",
}

_METHODS = ("card", "upi", "netbanking")


def pick_class(rng: random.Random) -> FailureClass:
    """One failure class, weighted by FAILURE_CLASS_MIX."""
    classes = list(FAILURE_CLASS_MIX)
    weights = list(FAILURE_CLASS_MIX.values())
    return rng.choices(classes, weights=weights, k=1)[0]


def build_failure_event(
    rng: random.Random, *, failure_class: FailureClass, is_mandate: bool = False
) -> dict[str, Any]:
    """One synthetic `payment.failed` webhook body.

    Amounts are randomised Rs 199-4,999 (paise) — typical small-ticket Indian
    checkout/subscription range. `order_id`/`id` are fresh per call so
    `handle_payment_failed`'s one-case-per-order UNIQUE constraint never
    collides across a batch.
    """
    amount_paise = rng.randint(19_900, 499_900)
    method = "upi" if is_mandate else rng.choice(_METHODS)
    entity: dict[str, Any] = {
        "id": f"pay_{uuid4().hex[:14]}",
        "order_id": f"order_{uuid4().hex[:14]}",
        "amount": amount_paise,
        "currency": "INR",
        "method": method,
        "email": f"demo+{uuid4().hex[:8]}@example.com",
        "error_reason": _ERROR_REASON_BY_CLASS[failure_class],
    }
    if is_mandate:
        entity["subscription_id"] = f"sub_{uuid4().hex[:14]}"
    return {"event": "payment.failed", "payload": {"payment": {"entity": entity}}}


def seed_batch(session: Any, *, count: int, seed: int | None = None) -> dict[str, Any]:
    """Seed `count` synthetic failed payments in-process.

    Deliberately does NOT write a `webhook_events` row the way the real
    ingress route does — that table exists to make a real Razorpay delivery
    replayable, and there is no delivery to replay here. Calling
    `handle_payment_failed` directly still produces a real `Case`, a real
    arm assignment, and a real audit trail, which is everything the
    dashboard, timeline and escalation queue actually read.
    `scripts/seed_failures.py` goes through the full HTTP route instead,
    specifically to demonstrate the real signature-verified path on camera.

    Guarantees at least one HARD_DECLINE case, and flags exactly one of them
    `demo_loose_prompt=True` so the poller's next `advance_case` pass on it
    triggers the hard-decline demo beat (BUILD-PLAN.md, video beat 3:00).

    Returns a summary — counts by class and by arm — so the operator can
    confirm the ~20% holdout before a live demo.
    """
    rng = random.Random(seed)
    classes = [pick_class(rng) for _ in range(count)]
    if FailureClass.HARD_DECLINE not in classes:
        classes[0] = FailureClass.HARD_DECLINE

    by_class: Counter[str] = Counter()
    by_arm: Counter[str] = Counter()
    loose_prompt_assigned = False

    for failure_class in classes:
        is_mandate = failure_class is FailureClass.SOFT_FUNDS and rng.random() < 0.4
        event = build_failure_event(rng, failure_class=failure_class, is_mandate=is_mandate)
        case_id = handle_payment_failed(session, event)
        case = session.get(Case, case_id)

        by_class[failure_class.value] += 1
        by_arm[case.arm] += 1

        if failure_class is FailureClass.HARD_DECLINE and not loose_prompt_assigned:
            case.demo_loose_prompt = True
            loose_prompt_assigned = True

    session.commit()
    # camelCase to match the rest of the API surface (schemas/api.py's
    # CamelModel) — this endpoint returns a plain dict rather than a
    # Pydantic model, so nothing enforces that consistency automatically.
    return {"count": count, "byClass": dict(by_class), "byArm": dict(by_arm)}
