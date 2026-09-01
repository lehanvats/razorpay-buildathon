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

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.agent.diagnose import DiagnosisFailed, diagnose
from app.core.holdout import Arm, assign_arm
from app.core.taxonomy import FailureClass, classify
from app.db.models import Action, Case, Outcome
from app.policy.gate import gate
from app.policy.rules import MAX_CHARGE_ATTEMPTS, MAX_MESSAGES_PER_CASE
from app.policy.snapshot import CaseSnapshot
from app.scheduler.poller import SchedulingFailed
from app.scheduler.poller import cancel as cancel_scheduled_action
from app.scheduler.poller import schedule as schedule_action
from app.schemas.proposal import ActionKind, Decision

#: Once a case reaches one of these, advance_case is a no-op — re-entrant
#: calls (e.g. a retried scheduler tick, once step-06 exists) must not
#: re-diagnose a case that already stopped.
_TERMINAL_STATUSES = frozenset({"recovered", "escalated", "exhausted"})


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

    # Deliberately NOT calling advance_case here, even for actionable
    # (treatment) cases: advance_case calls diagnose(), a synchronous LLM
    # round-trip, and running that inline would blow Razorpay's fast-2xx
    # expectation. Instead the case is left `status == "open"` with
    # `last_diagnosed_at IS NULL`, and scheduler.poller.claim_new_cases
    # picks it up on its next tick, off the request path entirely. See that
    # module's docstring for why a poller pass was chosen over a FastAPI
    # BackgroundTask on this route.

    return case_id


def _build_case_context(case: Case, *, now: datetime) -> dict:
    """Flatten a Case row into the plain dict agent/prompts.build_case_prompt
    expects. See that function's docstring for the required shape."""
    return {
        "case_id": case.id,
        "failure_class": case.failure_class,
        "amount_paise": case.amount_paise,
        "method": case.method,
        "is_mandate": case.is_mandate,
        "attempts_used": case.attempts_used,
        "max_attempts": MAX_CHARGE_ATTEMPTS,
        "messages_sent": case.messages_sent,
        "max_messages": MAX_MESSAGES_PER_CASE,
        "last_contact_at": case.last_contact_at.isoformat() if case.last_contact_at else None,
        "pre_debit_notice_sent_at": (
            case.pre_debit_notice_sent_at.isoformat() if case.pre_debit_notice_sent_at else None
        ),
        "now": now.isoformat(),
    }


def _build_snapshot(case: Case, *, now: datetime) -> CaseSnapshot:
    """Flatten a Case row into the gate's pure input contract."""
    return CaseSnapshot(
        case_id=case.id,
        amount_paise=case.amount_paise,
        method=case.method,
        failure_class=FailureClass(case.failure_class),
        arm=Arm(case.arm),
        attempts_used=case.attempts_used,
        is_mandate=case.is_mandate,
        pre_debit_notice_sent_at=case.pre_debit_notice_sent_at,
        messages_sent=case.messages_sent,
        last_contact_at=case.last_contact_at,
        discount_already_offered=case.discount_offered,
        now=now,
    )


def advance_case(session: Any, case_id: str) -> None:
    """Run one diagnose -> gate -> act cycle for a treated case.

    Called on case creation and again after any scheduled action completes
    without recovering. Re-entrant and safe to call twice: it no-ops on cases
    that are recovered, escalated or exhausted.

    Refuses to run on control cases — asserts rather than silently returning,
    because a control case reaching this function means the branch above is
    broken and silence would corrupt the headline metric.

    Not called anywhere yet — see the TODO(step-06) at its one intended call
    site in handle_payment_failed. What's implemented here (diagnose, gate,
    and the resulting escalate/block/approve branching) is complete and
    tested on its own; only the "act on an APPROVE/REWRITE verdict" half
    waits on step-06's `actions` table, noted inline below.
    """
    case = session.get(Case, case_id)
    assert case is not None, f"advance_case called for unknown case {case_id}"
    assert case.arm != Arm.CONTROL.value, (
        f"advance_case called on control case {case_id} — control cases "
        "never receive any action; this is a bug in the caller, not "
        "something to silently skip."
    )

    if case.status in _TERMINAL_STATUSES:
        return

    now = datetime.now(UTC)

    try:
        proposal = diagnose(_build_case_context(case, now=now))
    except DiagnosisFailed as exc:
        escalate(session, case_id, rule_id="DIAGNOSIS_FAILED", reason=str(exc))
        return

    verdict = gate(_build_snapshot(case, now=now), proposal)

    if verdict.decision == Decision.ESCALATE:
        escalate(session, case_id, rule_id=verdict.rule_id, reason=verdict.explanation)
        return

    if verdict.effective_action == ActionKind.ESCALATE:
        # The LLM itself proposed escalation and no rule overrode it — still
        # a compliant escalation, just one the model initiated rather than
        # the gate. Give it its own rule_id so the two are distinguishable
        # in the queue rather than both showing "PASS".
        escalate(session, case_id, rule_id="LLM_REQUESTED_ESCALATION", reason=proposal.reasoning)
        return

    if verdict.decision == Decision.BLOCK:
        if verdict.rule_id == "ATTEMPT_BUDGET_EXHAUSTED":
            # The one BLOCK rule that means "permanently stop", not just
            # "not this proposal" — attempt_budget's own docstring says NPCI
            # caps the retry count "then stop permanently". HARD_DECLINE_BLOCK
            # is deliberately NOT given the same treatment here: an existing
            # step-05 test (test_advance_case_does_not_touch_the_case_on_a_
            # blocked_proposal) pins `status` unchanged on that path, and
            # hard-decline cases have no action-driven exit condition the way
            # attempt exhaustion does — see corrections.md for the residual
            # gap this leaves.
            case.status = "exhausted"
            session.flush()
        # TODO(step-07): audit.record(session, case_id=case_id, actor=Actor.POLICY,
        #   event_type=EventType.POLICY_BLOCKED, payload={"rule_id": verdict.rule_id})
        return

    # APPROVE or REWRITE: verdict.effective_action/effective_timing is what
    # should actually run. Deliberately not touching attempts_used /
    # messages_sent here — that would claim an attempt was spent before any
    # executor has actually spent it. Those counters are owned by the
    # executors themselves (see executors/retry.py, executors/dunning.py),
    # in the same transaction as the network call they describe.
    try:
        schedule_action(
            session,
            case_id=case_id,
            kind=verdict.effective_action,
            verdict=verdict,
            run_at=verdict.effective_timing or now,
        )
    except SchedulingFailed as exc:
        # The eager pre-debit notice (for a mandate's first retry) failed to
        # send. No Action row was written, so there is nothing pending to
        # cancel — escalate rather than silently leaving the case "open"
        # with last_diagnosed_at already stamped, which would make it
        # unreachable by claim_new_cases forever.
        escalate(session, case_id, rule_id="SCHEDULING_FAILED", reason=str(exc))
        return
    case.status = "scheduled"
    session.flush()
    # TODO(step-07): audit.record(session, case_id=case_id, actor=Actor.POLICY,
    #   event_type=EventType.POLICY_APPROVED, payload={"rule_id": verdict.rule_id})


#: Maps a *successfully executed* action's kind to Outcome.via. OFFER_DISCOUNT
#: is realised through the same PaymentLinkExecutor as SEND_PAYMENT_LINK (a
#: discounted link), so it reports the same via.
_VIA_BY_ACTION_KIND = {
    ActionKind.SCHEDULE_RETRY.value: "retry",
    ActionKind.SEND_PAYMENT_LINK.value: "payment_link",
    ActionKind.OFFER_DISCOUNT.value: "payment_link",
}


def _derive_via(session: Any, case_id: str) -> str:
    """How the money actually came back, for `Outcome.via`.

    Reads the case's most recent *successful* Action row. No such row means
    no action has ever completed for this case — either it's a control case,
    the agent hasn't acted yet, or every attempted action failed — so "self"
    is the only truthful value, not an approximation.
    """
    action = session.execute(
        select(Action)
        .where(Action.case_id == case_id, Action.result.is_(True))
        .order_by(Action.executed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if action is None:
        return "self"
    return _VIA_BY_ACTION_KIND.get(action.kind, "self")


def _find_case_by_payment_link_reference(session: Any, payload: dict) -> Case | None:
    """Fallback correlation for `payment_link.paid`.

    A payment link is its own new Razorpay Order, so its `order_id` never
    matches `cases.razorpay_order_id` — see corrections.md. Instead,
    `integrations.razorpay_client.create_payment_link` stamps the link's
    `reference_id` with the case id, and that is what this reads back.
    """
    reference_id = payload.get("payment_link", {}).get("entity", {}).get("reference_id")
    if not reference_id:
        return None
    return session.get(Case, reference_id)


def _cancel_pending_actions(session: Any, case_id: str) -> None:
    """Cancel every not-yet-executed action for a case that just recovered.

    Charging (or messaging) a customer who has already paid is the worst bug
    this system could ship.
    """
    pending = session.execute(
        select(Action.id).where(Action.case_id == case_id, Action.executed_at.is_(None))
    ).scalars()
    for action_id in pending:
        cancel_scheduled_action(session, action_id)


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

    Two kinds of no-op are expected and NOT errors:
      - No case for this order (most successful payments never failed first;
        this handler only closes the loop for orders that did).
      - A case that already has an outcome (Razorpay fires more than one of
        these three event types for a single recovery — e.g. payment.captured
        AND order.paid — and each redelivers independently).

    `order_id` is read with `.get`, not `[...]`, specifically so a
    `payment_link.paid` payload that omits it (or omits `payment` entirely)
    falls through to the `reference_id` lookup instead of raising — the
    general malformed-payload story is still step-07's (see corrections.md
    #1), but this one specific path needs to reach the fallback to be
    reachable at all.
    """
    payload = event.get("payload", {})
    entity = payload.get("payment", {}).get("entity", {})
    order_id = entity.get("order_id")

    case = None
    if order_id:
        case = session.execute(
            select(Case).where(Case.razorpay_order_id == order_id)
        ).scalar_one_or_none()
    if case is None:
        case = _find_case_by_payment_link_reference(session, payload)
    if case is None:
        return

    existing_outcome = session.get(Outcome, case.id)
    if existing_outcome is not None:
        return

    amount_paise = entity.get("amount")
    if amount_paise is None:
        amount_paise = payload.get("payment_link", {}).get("entity", {}).get("amount_paid")
    if amount_paise is None:
        amount_paise = case.amount_paise

    outcome = Outcome(
        case_id=case.id,
        recovered_amount_paise=amount_paise,
        recovered_at=datetime.now(UTC),
        via=_derive_via(session, case.id),
        arm_at_recovery=case.arm,
    )
    session.add(outcome)

    case.status = "recovered"
    case.closed_at = outcome.recovered_at
    _cancel_pending_actions(session, case.id)
    # TODO(step-07): audit.record(session, case_id=case.id, actor=Actor.WEBHOOK,
    #   event_type=EventType.RECOVERED, payload={"amount_paise": amount_paise})

    session.flush()


def escalate(session: Any, case_id: str, *, rule_id: str, reason: str) -> None:
    """Move a case to the human queue and silence the agent on it.

    After escalation no further automated action is taken. Silence is the
    correct behaviour under the stopping rule, not a stalled case.

    Idempotent by construction: re-escalating the same case just overwrites
    the rule_id/reason with the latest verdict rather than erroring, since a
    case can only be in one escalated state at a time.
    """
    case = session.get(Case, case_id)
    if case is None:
        return

    case.status = "escalated"
    case.escalated_at = datetime.now(UTC)
    case.escalation_rule_id = rule_id
    case.escalation_reason = reason
    # TODO(step-07): audit.record(session, case_id=case_id, actor=Actor.POLICY,
    #   event_type=EventType.ESCALATED, payload={"rule_id": rule_id, "reason": reason})

    session.flush()


def get_timeline(session: Any, case_id: str) -> list[dict]:
    """Read the append-only audit trail for the case-detail view."""
    raise NotImplementedError("step-07: timeline rendering")
