"""The one scheduler implementation: claim, notify, dispatch, repeat.

Runs as a separate process (`python -m app.scheduler.poller`) alongside the
API, or as a periodic invocation on a host that offers one. Stateless — all
state is the `actions` table plus `cases.status`/`last_diagnosed_at` — so it
can be restarted or run redundantly.

Two independent claim loops share this module, both for the same reason
(durable delay, no in-memory state):

  * `claim_due_actions` / `dispatch` — approved actions whose `scheduled_for`
    has arrived.
  * `claim_new_cases` — treatment cases nobody has diagnosed yet. This is
    step-06's answer to the TODO(step-06) left in
    `services/case_manager.handle_payment_failed`: `advance_case` calls
    `diagnose()`, a synchronous LLM round-trip that must never run inline in
    the webhook handler (Razorpay expects a fast 2xx). Routing the first
    diagnosis through this same poller — rather than a FastAPI
    BackgroundTask on the request path — means the LLM call only ever runs
    here, in one process, on one cadence, with no risk of a webhook-test
    posting through TestClient triggering a real (unconfigured, in test) LLM
    call as a side effect of an unrelated assertion.

Claiming must be atomic in both loops. Two pollers, or one poller restarted
mid-batch, must never dispatch the same action — or diagnose the same case —
twice:

    UPDATE actions SET claimed_at = now()
    WHERE id IN (
        SELECT id FROM actions
        WHERE executed_at IS NULL AND claimed_at IS NULL
          AND scheduled_for <= now()
        ORDER BY scheduled_for
        LIMIT :batch
        FOR UPDATE SKIP LOCKED
    ) RETURNING id

`FOR UPDATE SKIP LOCKED` is the whole trick; without it the double-charge
risk (for actions) or the double-LLM-call risk (for cases) is real rather
than theoretical. Each claim commits immediately after stamping its marker
column, releasing the row lock before any slow network/LLM call runs — the
alternative (holding the lock across the call) would serialise a whole batch
behind one slow request. A single-process poller accepts the resulting
narrow window (another claimer could theoretically grab a just-released row
before this process finishes the first) the same way
`services/case_manager.py`'s webhook dedupe accepts its own read-then-write
race: real concurrent claimers don't exist in this build. See corrections.md.
"""

import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.audit import Actor, EventType
from app.core.audit import record as audit_record
from app.core.holdout import Arm
from app.db.models import Action, Case
from app.executors.base import ExecutionResult, Executor
from app.executors.dunning import DunningExecutor, PreDebitNoticeExecutor
from app.executors.payment_link import PaymentLinkExecutor
from app.executors.retry import RetryExecutor
from app.schemas.proposal import ActionKind, Verdict

log = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30
BATCH_SIZE = 25

MAX_ATTEMPTS_PER_ACTION = 3
"""Dispatch attempts — distinct from the NPCI *charge* attempt budget. This
counts transport failures (Razorpay 5xx, timeouts). A dispatch that never
reached Razorpay must not consume a regulatory retry; see
executors/retry.py for where the charge counter is incremented."""

#: One approved action can fan out to more than one executor step — see
#: executors/base.py:Executor.kind. PreDebitNoticeExecutor is deliberately
#: NOT here: it fires eagerly from `schedule()` below, not from this
#: deferred dispatch list.
EXECUTOR_REGISTRY: dict[ActionKind, list[Executor]] = {
    ActionKind.SCHEDULE_RETRY: [RetryExecutor()],
    ActionKind.SEND_PAYMENT_LINK: [PaymentLinkExecutor(), DunningExecutor()],
    ActionKind.OFFER_DISCOUNT: [PaymentLinkExecutor(), DunningExecutor()],
}


class SchedulingFailed(RuntimeError):
    """The eager pre-debit notice failed to send, so `schedule()` refused to
    write the Action row.

    Debiting a mandate customer who was never notified is the compliance
    breach `executors/base.py` exists to prevent -- see its module docstring.
    Callers (`services/case_manager.advance_case`) must catch this and
    escalate rather than mark the case scheduled.
    """


def schedule(
    session: Session,
    *,
    case_id: str,
    kind: ActionKind,
    verdict: Verdict,
    run_at: datetime,
) -> str:
    """Persist an action to run at `run_at`. Returns the action id.

    `payload_json` stores the *whole* verdict
    (`verdict.model_dump(mode="json")`), not a hand-picked subset of its
    fields — `dispatch()` reconstructs a `Verdict` from it via
    `Verdict.model_validate`, and the Executor protocol only ever sees that
    reconstructed Verdict, never this Action row.

    Fires `PreDebitNoticeExecutor` immediately, before the Action row is
    even written, when this is a mandate's first retry attempt. Discriminated
    on case state (`case.is_mandate and case.pre_debit_notice_sent_at is
    None`), NOT on `verdict.rule_id == PRE_DEBIT_NOTICE_REQUIRED`: gate()
    returns only the *last* rewriting rule's id, and `salary_window` runs
    after `pre_debit_notice` in RULE_CHAIN, so a mandate case that's also
    SOFT_FUNDS would report `SALARY_WINDOW_RESCHEDULE` even though the
    notice rule fired too. Case state is what the rule itself keys on, so it
    survives any future chain reordering.

    Raises `SchedulingFailed`, and writes no Action row, if that eager notice
    fails to send -- the alternative (scheduling the debit anyway) is the
    exact compliance breach the notice exists to prevent.
    """
    case = session.get(Case, case_id)
    if (
        kind is ActionKind.SCHEDULE_RETRY
        and case is not None
        and case.is_mandate
        and case.pre_debit_notice_sent_at is None
    ):
        notice_result = PreDebitNoticeExecutor().execute(session, case_id, verdict)
        if not notice_result.ok:
            raise SchedulingFailed(f"pre-debit notice failed to send: {notice_result.error}")

    action = Action(
        id=str(uuid4()),
        case_id=case_id,
        kind=kind.value,
        verdict_rule_id=verdict.rule_id,
        scheduled_for=run_at,
        payload_json=verdict.model_dump(mode="json"),
    )
    session.add(action)
    session.flush()
    audit_record(
        session,
        case_id=case_id,
        actor=Actor.SCHEDULER,
        event_type=EventType.ACTION_SCHEDULED,
        payload={"kind": kind.value, "scheduled_for": run_at.isoformat(), "action_id": action.id},
    )
    return action.id


def cancel(session: Session, action_id: str) -> None:
    """Cancel a not-yet-executed action.

    Needed when a case recovers on its own while a retry is pending —
    charging a customer who already paid is the worst bug this system
    could ship.
    """
    action = session.get(Action, action_id)
    if action is None or action.executed_at is not None:
        return
    _finalize_as_cancelled(action, "cancelled: case recovered before this action ran")
    session.flush()


def _finalize_as_cancelled(action: Action, reason: str) -> None:
    now = datetime.now(UTC)
    action.claimed_at = action.claimed_at or now
    action.executed_at = now
    action.result = False
    action.error = reason


def claim_due_actions(session: Session, limit: int = BATCH_SIZE) -> list[Action]:
    """Atomically claim up to `limit` actions whose time has come."""
    now = datetime.now(UTC)
    subquery = (
        select(Action.id)
        .where(
            Action.executed_at.is_(None),
            Action.claimed_at.is_(None),
            Action.scheduled_for <= now,
        )
        .order_by(Action.scheduled_for)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    ids = list(session.execute(subquery).scalars())
    if not ids:
        return []

    session.execute(update(Action).where(Action.id.in_(ids)).values(claimed_at=now))
    session.commit()  # release row locks before any network call runs

    claimed = session.execute(select(Action).where(Action.id.in_(ids))).scalars()
    return list(claimed)


def claim_new_cases(session: Session, limit: int = BATCH_SIZE) -> list[Case]:
    """Atomically claim up to `limit` treatment cases that have never been
    diagnosed. See the module docstring for why this exists alongside
    `claim_due_actions` rather than the webhook route calling `advance_case`
    directly.

    Gated on `last_diagnosed_at IS NULL`, not `status == "open"` alone: a
    proposal the gate BLOCKs (e.g. CONTACT_COOLDOWN) leaves a case "open"
    with no Action row, which is otherwise indistinguishable from one that
    was never diagnosed — see `db/models.py:Case.last_diagnosed_at`.
    """
    now = datetime.now(UTC)
    subquery = (
        select(Case.id)
        .where(
            Case.status == "open",
            Case.arm == Arm.TREATMENT.value,
            Case.last_diagnosed_at.is_(None),
        )
        .order_by(Case.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    ids = list(session.execute(subquery).scalars())
    if not ids:
        return []

    session.execute(update(Case).where(Case.id.in_(ids)).values(last_diagnosed_at=now))
    session.commit()  # release row locks before the LLM call runs

    claimed = session.execute(select(Case).where(Case.id.in_(ids))).scalars()
    return list(claimed)


def dispatch(session: Session, action: Action) -> None:
    """Route one claimed action to its executor(s).

    Re-checks the case is still `scheduled` before executing: a case that
    recovered on its own since scheduling has its pending action cancelled
    by `services/case_manager.handle_payment_succeeded`, but this is a
    second guard against the race where a payment lands between that cancel
    and this dispatch.
    """
    case = session.get(Case, action.case_id)
    if case is None or case.status != "scheduled":
        _finalize_as_cancelled(
            action,
            f"skipped: case status is {case.status if case else 'missing'}, not scheduled",
        )
        session.flush()
        return

    verdict = Verdict.model_validate(action.payload_json)
    executors = EXECUTOR_REGISTRY.get(ActionKind(action.kind), [])

    action.executed_at = datetime.now(UTC)  # claim before touching the network
    session.flush()

    ok = True
    error: str | None = None
    razorpay_ref: str | None = None
    for executor in executors:
        try:
            result: ExecutionResult = executor.execute(session, case.id, verdict)
        except Exception as exc:  # noqa: BLE001 -- a buggy executor must not
            # abort the whole tick; Executor.execute's contract (see
            # executors/base.py) says "must not raise", but this is the
            # backstop for the day one doesn't honor it.
            result = ExecutionResult(ok=False, error=str(exc))
        razorpay_ref = result.razorpay_ref or razorpay_ref
        if not result.ok:
            ok, error = False, result.error
            break  # don't email a discount link that was never created

    action.result = ok
    action.error = error
    action.razorpay_ref = razorpay_ref

    if not ok:
        action.dispatch_attempts += 1
        if action.dispatch_attempts < MAX_ATTEMPTS_PER_ACTION:
            # Release the claim so a later poll tick retries the transport
            # failure. Clearing executed_at alone would leave the row
            # invisible to claim_due_actions forever — its WHERE clause
            # also requires claimed_at IS NULL.
            action.executed_at = None
            action.claimed_at = None
            session.flush()
            return

        from app.services.case_manager import escalate  # local: avoid an import cycle

        escalate(
            session,
            case.id,
            rule_id="ACTION_DISPATCH_FAILED",
            reason=f"{action.kind} failed after {MAX_ATTEMPTS_PER_ACTION} dispatch "
            f"attempts: {error}",
        )
        session.flush()
        return

    # Success. The case isn't necessarily recovered yet (SEND_PAYMENT_LINK
    # / OFFER_DISCOUNT still need the customer to pay; SCHEDULE_RETRY's own
    # recovery arrives, if it does, through the same payment.captured path
    # as any other charge) — "awaiting_customer" covers both; it's the
    # closest fit in the documented status vocabulary and there is only one
    # such waiting state. handle_payment_succeeded moves it to "recovered"
    # when a later webhook confirms it did.
    case.status = "awaiting_customer"
    session.flush()


def run_forever() -> None:
    """Poll loop. Entry point for `python -m app.scheduler.poller`."""
    from app.db.session import SessionLocal
    from app.services.case_manager import advance_case

    log.info("scheduler poller starting: interval=%ss batch=%s", POLL_INTERVAL_SECONDS, BATCH_SIZE)
    while True:
        try:
            with SessionLocal() as session:
                for case in claim_new_cases(session):
                    advance_case(session, case.id)
                    session.commit()

                for action in claim_due_actions(session):
                    dispatch(session, action)
                    session.commit()
        except Exception:  # noqa: BLE001 — the loop must survive one bad tick
            log.exception("scheduler poller tick failed")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
