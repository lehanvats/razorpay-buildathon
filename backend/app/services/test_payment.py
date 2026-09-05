"""Operator-initiated test payment — the whole loop, with a real payment.

Everything the seeder and simulator do is synthetic: the failure, the
customer, the payment. This module keeps exactly one thing synthetic — the
abandoned checkout that opens the case — and makes the rest real:

    simulated payment.failed (DROPOFF)      -> case opened, arm, class
    operator proposes SEND_PAYMENT_LINK     -> the real policy gate disposes
    scheduler writes the Action             -> real PaymentLinkExecutor calls
                                               Razorpay (test mode), real link
    the operator pays on Razorpay checkout  -> payment_link.paid webhook
                                               AND/OR the callback redirect
    reconcile against Razorpay's API        -> handle_payment_succeeded,
                                               same path as every webhook

Nothing here bypasses the gate, and no executor is handed anything but a
Verdict the gate produced. What the operator supplies is a *proposal* — the
seat the LLM normally sits in — and the audit trail says so
(EventType.OPERATOR_PROPOSED, actor HUMAN), so a reader can never mistake a
test payment's timeline for a model-driven one.

Two ways the recovery lands, both idempotent, either order:
  * Razorpay's `payment_link.paid` webhook, when Razorpay can reach the API
    (`api/routes/webhooks.py` -> `handle_payment_succeeded`).
  * `reconcile()`, called by the `/pay/return` page the payer is redirected
    to. Verifies the redirect's signature, then fetches the link from
    Razorpay and — only if Razorpay says `paid` — closes the case through
    that same `handle_payment_succeeded`. This is the path that works on a
    laptop, where no webhook can arrive.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.config import settings
from app.core.audit import Actor, EventType
from app.core.audit import record as audit_record
from app.core.holdout import Arm, assign_arm
from app.db.models import Action, AuditEvent, Case, Outcome
from app.integrations.razorpay_client import (
    fetch_payment_link,
    verify_payment_link_callback_signature,
)
from app.policy.gate import gate
from app.scheduler.poller import dispatch, schedule
from app.schemas.proposal import ActionKind, Channel, Decision, Proposal
from app.services.case_manager import (
    _build_snapshot,
    handle_payment_failed,
    handle_payment_succeeded,
)

log = logging.getLogger(__name__)


class TestPaymentFailed(RuntimeError):
    """The link could not be created. `case_id` is set when a case was
    opened before the failure — the audit trail on it shows ACTION_FAILED
    with the executor's error, which is more useful to the operator than a
    bare 502."""

    def __init__(self, message: str, *, case_id: str | None = None):
        super().__init__(message)
        self.case_id = case_id


def _treatment_case_id() -> str:
    """A fresh uuid4 that `assign_arm` puts in the treatment arm.

    A test payment exists to exercise an action, and a control case never
    gets one. Rather than overriding the arm (which would make `arm` no
    longer recomputable from the id, breaking the audit property
    core/holdout.py promises), draw ids until one hashes to treatment — ~1.25
    draws on average at a 20% holdout. The arm is still a pure function of
    the stored id.
    """
    while True:
        candidate = str(uuid4())
        if assign_arm(candidate) is Arm.TREATMENT:
            return candidate


def _reasoning(amount_paise: int) -> str:
    return (
        "Operator-initiated test payment. The abandoned checkout that opened "
        f"this case is simulated; the Rs {amount_paise / 100:,.2f} payment link, "
        "the payment made against it and the recovery recorded below are real "
        "(Razorpay test mode). An abandoned checkout is a persuasion problem, "
        "not a timing one, so the proposal is a customer-authenticated payment "
        "link rather than an auto-charge — the same choice the model is "
        "prompted to make for DROPOFF."
    )


def _message_draft(amount_paise: int) -> str:
    return (
        f"Your payment of Rs {amount_paise / 100:,.2f} didn't go through. "
        "Complete it securely with the link below whenever you're ready."
    )


def create_test_payment(session: Any, *, amount_paise: int, customer_email: str) -> dict:
    """Open a case for a simulated abandoned checkout and drive it to a real
    Razorpay Payment Link, synchronously.

    Synchronous on purpose, unlike the webhook path: the operator is sitting
    on the page waiting to be redirected to the link, so the executor runs
    inline here rather than on the poller's 30s cadence. The steps are the
    same functions the poller would call (`schedule`, `dispatch`), so the
    Action row, status transitions and audit events are byte-for-byte what a
    poller-driven case produces.

    Returns a dict with `case_id`, `payment_link_id`, `payment_url`,
    `amount_paise`, `status`.

    Raises:
        TestPaymentFailed: the gate refused (cannot happen for a fresh
            DROPOFF case, but the gate is authoritative so it is checked) or
            the executor reported a failure. The case and its audit trail are
            committed before raising, so the failure is inspectable.
    """
    now = datetime.now(UTC)
    case_id = _treatment_case_id()

    # 1. The simulated failure. `payment_timed_out` is the error_reason
    #    `core.taxonomy` maps to DROPOFF (see services/seeding.py).
    event = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{uuid4().hex[:14]}",
                    "order_id": f"order_{uuid4().hex[:14]}",
                    "amount": amount_paise,
                    "currency": "INR",
                    "method": "upi",
                    "email": customer_email,
                    "error_reason": "payment_timed_out",
                }
            }
        },
    }
    handle_payment_failed(session, event, case_id=case_id)
    case = session.get(Case, case_id)

    # 2. The proposal — the operator in the LLM's seat, recorded as such.
    proposal = Proposal(
        action=ActionKind.SEND_PAYMENT_LINK,
        channel=Channel.EMAIL,
        confidence=1.0,
        reasoning=_reasoning(amount_paise),
        message_draft=_message_draft(amount_paise),
    )
    audit_record(
        session,
        case_id=case_id,
        actor=Actor.HUMAN,
        event_type=EventType.OPERATOR_PROPOSED,
        payload={"action": proposal.action.value, "reasoning": proposal.reasoning},
    )

    # 3. The gate disposes. Same call, same snapshot builder as advance_case.
    verdict = gate(_build_snapshot(case, now=now), proposal)
    if (
        verdict.decision not in (Decision.APPROVE, Decision.REWRITE)
        or verdict.effective_action is None
    ):
        audit_record(
            session,
            case_id=case_id,
            actor=Actor.POLICY,
            event_type=EventType.POLICY_BLOCKED,
            payload={"rule_id": verdict.rule_id},
        )
        session.commit()
        raise TestPaymentFailed(
            f"policy gate refused the payment link ({verdict.rule_id}): {verdict.explanation}",
            case_id=case_id,
        )

    # 4. Schedule and dispatch, exactly as the poller would — but now.
    #    last_diagnosed_at is stamped so claim_new_cases never picks this
    #    case up and spends an LLM call re-diagnosing something already acted
    #    on; `status = scheduled` is what dispatch() requires to run at all.
    action_id = schedule(
        session,
        case_id=case_id,
        kind=verdict.effective_action,
        verdict=verdict,
        run_at=now,
    )
    case.status = "scheduled"
    case.last_diagnosed_at = now
    session.flush()
    audit_record(
        session,
        case_id=case_id,
        actor=Actor.POLICY,
        event_type=EventType.POLICY_APPROVED,
        payload={"rule_id": verdict.rule_id},
    )

    action = session.get(Action, action_id)
    action.claimed_at = now  # what claim_due_actions would have stamped
    dispatch(session, action)
    session.commit()

    if not action.result:
        # dispatch() has already recorded ACTION_FAILED and either released
        # the claim for the poller to retry or escalated; both are the real
        # system's behaviour and both are visible on the case's timeline.
        raise TestPaymentFailed(
            f"payment link could not be created: {action.error}", case_id=case_id
        )

    # dispatch() keeps the executor's razorpay_ref on the Action row but
    # not its `detail` (the short URL); the ACTION_COMPLETED audit event
    # the executor wrote is where that lives. Reading it back from the
    # trail, rather than threading a new column through, keeps the audit
    # log the single record of what the executor did.
    completed = session.execute(
        select(AuditEvent)
        .where(
            AuditEvent.case_id == case_id,
            AuditEvent.event_type == EventType.ACTION_COMPLETED.value,
        )
        .order_by(AuditEvent.ts.desc(), AuditEvent.id.desc())
    ).scalars()
    payment_url = next(
        (
            e.payload_json.get("detail")
            for e in completed
            if e.payload_json.get("razorpay_ref") == action.razorpay_ref
            and e.payload_json.get("detail")
        ),
        None,
    )
    if not payment_url:
        raise TestPaymentFailed(
            "payment link was created but Razorpay returned no short_url", case_id=case_id
        )

    return {
        "case_id": case_id,
        "payment_link_id": action.razorpay_ref,
        "payment_url": payment_url,
        "amount_paise": amount_paise,
        "status": case.status,
    }


def _link_url(link: dict) -> str | None:
    return link.get("short_url") or None


def reconcile(
    session: Any,
    *,
    payment_link_id: str,
    payment_id: str | None,
    reference_id: str | None,
    link_status: str | None,
    signature: str | None,
) -> dict:
    """Close the loop from the payer's callback redirect.

    Order matters:
      1. If the redirect carried a signature, verify it (API key secret).
         A bad signature is rejected outright — someone edited the URL.
      2. Fetch the link from Razorpay. This, not the redirect's own
         `razorpay_payment_link_status`, decides whether money moved.
      3. Only if Razorpay says `paid` and the case has no outcome yet:
         record PAYMENT_VERIFIED and run `handle_payment_succeeded` with a
         `payment_link.paid`-shaped event built from the fetched link — the
         identical code path a webhook takes, so `Outcome.via`, pending-
         action cancellation and the RECOVERED event all come from one
         implementation.

    Idempotent: a refresh of the return page, or a webhook that already
    landed, makes step 3 a no-op (no second PAYMENT_VERIFIED, no second
    outcome).

    Returns a dict with `case_id`, `status` (Razorpay's link status),
    `recovered`, `amount_paise`, `payment_id`, `payment_url`,
    `signature_valid` (None when the redirect carried no signature).

    Raises:
        LookupError: no case matches `reference_id` / the link.
        PermissionError: the redirect's signature does not verify.
    """
    signature_valid: bool | None = None
    if signature:
        if not (payment_id and reference_id and link_status):
            raise PermissionError("callback signature present but its inputs are incomplete")
        signature_valid = verify_payment_link_callback_signature(
            payment_link_id=payment_link_id,
            reference_id=reference_id,
            link_status=link_status,
            payment_id=payment_id,
            signature=signature,
            secret=settings.razorpay_key_secret,
        )
        if not signature_valid:
            log.warning(
                "rejected payment-link callback with invalid signature (%s)", payment_link_id
            )
            raise PermissionError("invalid callback signature")

    link = fetch_payment_link(payment_link_id)
    case_ref = link.get("reference_id") or reference_id
    case = session.get(Case, case_ref) if case_ref else None
    if case is None:
        # The link's reference_id is authoritative; fall back to the Action
        # row that created it, for a link minted before reference_ids existed.
        action = session.execute(
            select(Action).where(Action.razorpay_ref == payment_link_id).limit(1)
        ).scalar_one_or_none()
        case = session.get(Case, action.case_id) if action else None
    if case is None:
        raise LookupError(f"no case for payment link {payment_link_id}")

    payments = link.get("payments") or []
    latest = payments[-1] if payments else {}
    paid_payment_id = latest.get("payment_id") or payment_id
    status = str(link.get("status") or link_status or "unknown")

    if status == "paid" and session.get(Outcome, case.id) is None:
        audit_record(
            session,
            case_id=case.id,
            actor=Actor.EXECUTOR,
            event_type=EventType.PAYMENT_VERIFIED,
            payload={
                "payment_link_id": payment_link_id,
                "payment_id": paid_payment_id,
                "signature_valid": signature_valid,
                "source": "callback",
            },
        )
        handle_payment_succeeded(
            session,
            {
                "event": "payment_link.paid",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": paid_payment_id,
                            "order_id": link.get("order_id"),
                            "amount": link.get("amount_paid")
                            or latest.get("amount")
                            or link.get("amount"),
                            "currency": link.get("currency", "INR"),
                            "method": latest.get("method"),
                        }
                    },
                    "payment_link": {
                        "entity": {
                            "id": link.get("id", payment_link_id),
                            "status": status,
                            "reference_id": case.id,
                            "amount_paid": link.get("amount_paid"),
                        }
                    },
                },
            },
        )
        session.commit()

    outcome = session.get(Outcome, case.id)
    return {
        "case_id": case.id,
        "status": status,
        "recovered": outcome is not None,
        "amount_paise": outcome.recovered_amount_paise if outcome else case.amount_paise,
        "payment_id": paid_payment_id,
        "payment_url": _link_url(link),
        "signature_valid": signature_valid,
    }
