"""Scheduler tests: claiming (both loops), scheduling, cancellation, and
dispatch's success/failure/skip branches.

Network calls never happen here — dispatch() routes through
EXECUTOR_REGISTRY, whose executors are monkeypatched at the same module
boundary tests/test_executors.py uses (`app.executors.<module>.<fn>`).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.audit import EventType
from app.db.models import Action, AuditEvent, Case
from app.scheduler.poller import (
    MAX_ATTEMPTS_PER_ACTION,
    cancel,
    claim_due_actions,
    claim_new_cases,
    dispatch,
    schedule,
)
from app.schemas.proposal import ActionKind, Decision, Verdict


def _make_case(db_session, **overrides) -> Case:
    defaults = dict(
        id="case_sched_test",
        razorpay_order_id="order_SCHED",
        razorpay_payment_id="pay_SCHED",
        customer_email="customer@example.com",
        amount_paise=149_900,
        currency="INR",
        method="upi",
        is_mandate=False,
        failure_class="SOFT_TECHNICAL",
        arm="treatment",
        status="open",
        attempts_used=1,
        messages_sent=0,
        discount_offered=False,
    )
    defaults.update(overrides)
    case = Case(**defaults)
    db_session.add(case)
    db_session.flush()
    return case


def _verdict(**overrides) -> Verdict:
    defaults = dict(
        decision=Decision.APPROVE,
        rule_id="PASS",
        effective_action=ActionKind.SCHEDULE_RETRY,
        explanation="test",
    )
    defaults.update(overrides)
    return Verdict(**defaults)


# --- schedule() -----------------------------------------------------


def test_schedule_writes_an_action_row_with_the_full_verdict(db_session):
    case = _make_case(db_session)
    run_at = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)

    action_id = schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SCHEDULE_RETRY,
        verdict=_verdict(rule_id="SALARY_WINDOW_RESCHEDULE", effective_timing=run_at),
        run_at=run_at,
    )

    action = db_session.get(Action, action_id)
    assert action.case_id == case.id
    assert action.kind == ActionKind.SCHEDULE_RETRY.value
    assert action.scheduled_for == run_at
    assert action.executed_at is None
    assert action.payload_json["rule_id"] == "SALARY_WINDOW_RESCHEDULE"


def test_schedule_writes_an_action_scheduled_event(db_session):
    case = _make_case(db_session)
    run_at = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)

    action_id = schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SCHEDULE_RETRY,
        verdict=_verdict(),
        run_at=run_at,
    )

    event = db_session.query(AuditEvent).filter_by(case_id=case.id).one()
    assert event.event_type == EventType.ACTION_SCHEDULED.value
    assert event.payload_json == {
        "kind": ActionKind.SCHEDULE_RETRY.value,
        "scheduled_for": run_at.isoformat(),
        "action_id": action_id,
    }


def test_schedule_fires_pre_debit_notice_eagerly_for_an_unnotified_mandate(db_session, monkeypatch):
    """Discriminated on case state, not verdict.rule_id — see the module
    docstring on why rule_id alone (e.g. SALARY_WINDOW_RESCHEDULE winning
    over PRE_DEBIT_NOTICE_REQUIRED in the chain) can't be trusted here."""
    case = _make_case(db_session, is_mandate=True)
    assert case.pre_debit_notice_sent_at is None
    monkeypatch.setattr("app.executors.dunning.send_email", lambda *a, **kw: "msg_notice")

    schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SCHEDULE_RETRY,
        verdict=_verdict(rule_id="SALARY_WINDOW_RESCHEDULE"),
        run_at=datetime.now(UTC) + timedelta(hours=24),
    )

    assert db_session.get(Case, case.id).pre_debit_notice_sent_at is not None


def test_schedule_does_not_fire_notice_when_already_sent(db_session, monkeypatch):
    already = datetime.now(UTC) - timedelta(hours=1)
    case = _make_case(db_session, is_mandate=True, pre_debit_notice_sent_at=already)

    def _fail(*a, **kw):
        raise AssertionError("must not re-send an already-sent pre-debit notice")

    monkeypatch.setattr("app.executors.dunning.send_email", _fail)

    schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SCHEDULE_RETRY,
        verdict=_verdict(),
        run_at=datetime.now(UTC),
    )

    assert db_session.get(Case, case.id).pre_debit_notice_sent_at == already


def test_schedule_does_not_fire_notice_for_non_mandate_cases(db_session, monkeypatch):
    case = _make_case(db_session, is_mandate=False)

    def _fail(*a, **kw):
        raise AssertionError("non-mandate cases never get a pre-debit notice")

    monkeypatch.setattr("app.executors.dunning.send_email", _fail)

    schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SCHEDULE_RETRY,
        verdict=_verdict(),
        run_at=datetime.now(UTC),
    )

    assert db_session.get(Case, case.id).pre_debit_notice_sent_at is None


# --- cancel() -----------------------------------------------------


def test_cancel_finalizes_a_pending_action(db_session):
    case = _make_case(db_session)
    action_id = schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SCHEDULE_RETRY,
        verdict=_verdict(),
        run_at=datetime.now(UTC) + timedelta(hours=1),
    )

    cancel(db_session, action_id)

    action = db_session.get(Action, action_id)
    assert action.executed_at is not None
    assert action.result is False


def test_cancel_is_a_noop_on_an_already_executed_action(db_session):
    case = _make_case(db_session)
    action_id = schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SCHEDULE_RETRY,
        verdict=_verdict(),
        run_at=datetime.now(UTC),
    )
    action = db_session.get(Action, action_id)
    action.executed_at = datetime.now(UTC)
    action.result = True
    action.razorpay_ref = "order_ALREADY_RAN"
    db_session.flush()

    cancel(db_session, action_id)

    assert db_session.get(Action, action_id).razorpay_ref == "order_ALREADY_RAN"


# --- claim_due_actions() -----------------------------------------------------


def test_claim_due_actions_claims_only_due_unclaimed_rows(db_session):
    case = _make_case(db_session)
    due_id = schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SCHEDULE_RETRY,
        verdict=_verdict(),
        run_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    future_id = schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SCHEDULE_RETRY,
        verdict=_verdict(),
        run_at=datetime.now(UTC) + timedelta(hours=1),
    )

    claimed = claim_due_actions(db_session)

    claimed_ids = {a.id for a in claimed}
    assert due_id in claimed_ids
    assert future_id not in claimed_ids
    assert db_session.get(Action, due_id).claimed_at is not None


def test_claim_due_actions_does_not_reclaim_already_claimed_rows(db_session):
    case = _make_case(db_session)
    action_id = schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SCHEDULE_RETRY,
        verdict=_verdict(),
        run_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    first_pass = claim_due_actions(db_session)
    second_pass = claim_due_actions(db_session)

    assert [a.id for a in first_pass] == [action_id]
    assert second_pass == []


# --- claim_new_cases() -----------------------------------------------------


def test_claim_new_cases_claims_only_undiagnosed_treatment_cases(db_session):
    fresh = _make_case(db_session, id="case_fresh", razorpay_order_id="order_FRESH")
    control = _make_case(
        db_session, id="case_control", razorpay_order_id="order_CONTROL", arm="control"
    )
    already_diagnosed = _make_case(
        db_session,
        id="case_diag",
        razorpay_order_id="order_DIAG",
        last_diagnosed_at=datetime.now(UTC),
    )

    claimed = claim_new_cases(db_session)

    claimed_ids = {c.id for c in claimed}
    assert fresh.id in claimed_ids
    assert control.id not in claimed_ids
    assert already_diagnosed.id not in claimed_ids
    assert db_session.get(Case, fresh.id).last_diagnosed_at is not None


def test_claim_new_cases_does_not_reclaim_on_a_second_pass(db_session):
    case = _make_case(db_session)

    first_pass = claim_new_cases(db_session)
    second_pass = claim_new_cases(db_session)

    assert [c.id for c in first_pass] == [case.id]
    assert second_pass == []


# --- dispatch() -----------------------------------------------------


def test_dispatch_skips_a_case_that_is_no_longer_scheduled(db_session):
    """A payment landed (or the case moved on) between scheduling and this
    poll tick — dispatch must not run the action anyway."""
    case = _make_case(db_session, status="recovered")
    action_id = schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SCHEDULE_RETRY,
        verdict=_verdict(),
        run_at=datetime.now(UTC),
    )
    action = db_session.get(Action, action_id)

    dispatch(db_session, action)

    updated = db_session.get(Action, action_id)
    assert updated.executed_at is not None
    assert updated.result is False


def test_dispatch_runs_executors_and_marks_the_case_awaiting_customer(db_session, monkeypatch):
    case = _make_case(db_session, status="scheduled")
    monkeypatch.setattr(
        "app.executors.retry.create_order", lambda *a, **kw: {"id": "order_DISPATCHED"}
    )
    action_id = schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SCHEDULE_RETRY,
        verdict=_verdict(),
        run_at=datetime.now(UTC),
    )
    action = db_session.get(Action, action_id)

    dispatch(db_session, action)

    updated_action = db_session.get(Action, action_id)
    assert updated_action.result is True
    assert updated_action.razorpay_ref == "order_DISPATCHED"
    assert db_session.get(Case, case.id).status == "awaiting_customer"
    assert db_session.get(Case, case.id).attempts_used == 2


def test_dispatch_releases_the_claim_on_a_transport_failure_with_retries_left(
    db_session, monkeypatch
):
    case = _make_case(db_session, status="scheduled")

    def _raise(*a, **kw):
        raise RuntimeError("timeout")

    monkeypatch.setattr("app.executors.retry.create_order", _raise)
    action_id = schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SCHEDULE_RETRY,
        verdict=_verdict(),
        run_at=datetime.now(UTC),
    )
    action = db_session.get(Action, action_id)

    dispatch(db_session, action)

    updated = db_session.get(Action, action_id)
    assert updated.dispatch_attempts == 1
    assert updated.executed_at is None  # released for a future retry
    assert updated.claimed_at is None
    assert db_session.get(Case, case.id).status == "scheduled"  # untouched


def test_dispatch_runs_the_full_send_payment_link_fan_out(db_session, monkeypatch):
    """SEND_PAYMENT_LINK composes two executors in order (create the link,
    then email it) — and the message_draft/channel the LLM wrote must
    survive the payload_json round-trip to reach DunningExecutor, which
    never sees the original Proposal."""
    case = _make_case(db_session, status="scheduled")
    monkeypatch.setattr(
        "app.executors.payment_link.create_payment_link",
        lambda *a, **kw: {"id": "plink_FANOUT", "short_url": "https://rzp.io/y"},
    )
    sent = {}
    monkeypatch.setattr(
        "app.executors.dunning.send_email",
        lambda to, subject, body: sent.setdefault("body", body) or "msg_fanout",
    )

    action_id = schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SEND_PAYMENT_LINK,
        verdict=_verdict(
            effective_action=ActionKind.SEND_PAYMENT_LINK,
            message_draft="Here is your payment link.",
        ),
        run_at=datetime.now(UTC),
    )
    action = db_session.get(Action, action_id)

    dispatch(db_session, action)

    assert sent["body"] == "Here is your payment link."
    updated_action = db_session.get(Action, action_id)
    assert updated_action.result is True
    assert updated_action.razorpay_ref == "plink_FANOUT"
    updated_case = db_session.get(Case, case.id)
    assert updated_case.status == "awaiting_customer"
    assert updated_case.messages_sent == 1

    # Both fan-out executors are audited via with_audit, in the order they
    # ran, alongside schedule()'s own ACTION_SCHEDULED event.
    events = (
        db_session.query(AuditEvent)
        .filter_by(case_id=case.id)
        .order_by(AuditEvent.ts, AuditEvent.id)
        .all()
    )
    assert [e.event_type for e in events] == [
        EventType.ACTION_SCHEDULED.value,
        EventType.ACTION_STARTED.value,
        EventType.ACTION_COMPLETED.value,
        EventType.ACTION_STARTED.value,
        EventType.ACTION_COMPLETED.value,
    ]
    assert events[1].payload_json == {"kind": ActionKind.SEND_PAYMENT_LINK.value}
    assert events[2].payload_json["razorpay_ref"] == "plink_FANOUT"


def test_dispatch_does_not_rerun_an_already_succeeded_fan_out_executor_on_retry(
    db_session, monkeypatch
):
    """Regression (corrections.md #12): SEND_PAYMENT_LINK fans out to
    PaymentLinkExecutor then DunningExecutor. If the link succeeds but the
    email transport fails, dispatch() releases the claim for retry — the old
    code re-ran the loop from the top on the next attempt, which would create
    a SECOND real, live payment link. The fix must call PaymentLinkExecutor
    exactly once across both attempts, and DunningExecutor once it succeeds
    on the retry."""
    case = _make_case(db_session, status="scheduled")

    link_calls = []
    monkeypatch.setattr(
        "app.executors.payment_link.create_payment_link",
        lambda *a, **kw: (
            link_calls.append(1),
            {"id": "plink_ONCE", "short_url": "https://rzp.io/y"},
        )[1],
    )

    email_calls = {"count": 0}

    def _flaky_send_email(to, subject, body):
        email_calls["count"] += 1
        if email_calls["count"] == 1:
            raise RuntimeError("timeout")
        return "msg_retry"

    monkeypatch.setattr("app.executors.dunning.send_email", _flaky_send_email)

    action_id = schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SEND_PAYMENT_LINK,
        verdict=_verdict(
            effective_action=ActionKind.SEND_PAYMENT_LINK,
            message_draft="Here is your payment link.",
        ),
        run_at=datetime.now(UTC),
    )

    # First attempt: link succeeds, email fails -> released for retry.
    action = db_session.get(Action, action_id)
    dispatch(db_session, action)
    after_first = db_session.get(Action, action_id)
    assert after_first.result is False
    assert after_first.executed_at is None  # released
    assert after_first.completed_executors == ["PaymentLinkExecutor"]
    assert after_first.razorpay_ref == "plink_ONCE"  # preserved across the retry

    # Second attempt: PaymentLinkExecutor must be skipped; only the email
    # (now succeeding) runs.
    action = db_session.execute(select(Action).where(Action.id == action_id)).scalar_one()
    dispatch(db_session, action)

    updated_action = db_session.get(Action, action_id)
    assert updated_action.result is True
    assert updated_action.razorpay_ref == "plink_ONCE"
    assert len(link_calls) == 1  # never re-created
    assert email_calls["count"] == 2  # one failure, one success
    assert set(updated_action.completed_executors) == {"PaymentLinkExecutor", "DunningExecutor"}


def test_dispatch_survives_an_executor_that_raises_instead_of_reporting_failure(
    db_session, monkeypatch
):
    """Executor.execute's contract (executors/base.py) says 'must not raise'.
    dispatch()'s loop is the backstop for the day one doesn't honor it: a
    raising executor must become a failed ExecutionResult, not abort the
    whole tick before `action.result`/`dispatch_attempts` are ever written."""
    case = _make_case(db_session, status="scheduled")
    monkeypatch.setattr(
        "app.executors.payment_link.create_payment_link",
        lambda *a, **kw: {"id": "plink_BUGGY", "short_url": "https://rzp.io/z"},
    )

    def _raise(*a, **kw):
        raise RuntimeError("executor bug, not a reported ExecutionResult")

    monkeypatch.setattr("app.executors.dunning.DunningExecutor.execute", _raise)

    action_id = schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SEND_PAYMENT_LINK,
        verdict=_verdict(
            effective_action=ActionKind.SEND_PAYMENT_LINK,
            message_draft="Here is your payment link.",
        ),
        run_at=datetime.now(UTC),
    )
    action = db_session.get(Action, action_id)

    dispatch(db_session, action)  # must not raise

    updated_action = db_session.get(Action, action_id)
    assert updated_action.dispatch_attempts == 1
    assert "executor bug" in updated_action.error
    assert db_session.get(Case, case.id).status == "scheduled"  # untouched


def test_dispatch_escalates_after_exhausting_dispatch_attempts(db_session, monkeypatch):
    case = _make_case(db_session, status="scheduled")

    def _raise(*a, **kw):
        raise RuntimeError("timeout")

    monkeypatch.setattr("app.executors.retry.create_order", _raise)
    action_id = schedule(
        db_session,
        case_id=case.id,
        kind=ActionKind.SCHEDULE_RETRY,
        verdict=_verdict(),
        run_at=datetime.now(UTC),
    )

    for _ in range(MAX_ATTEMPTS_PER_ACTION):
        action = db_session.execute(select(Action).where(Action.id == action_id)).scalar_one()
        dispatch(db_session, action)

    updated_case = db_session.get(Case, case.id)
    assert updated_case.status == "escalated"
    assert updated_case.escalation_rule_id == "ACTION_DISPATCH_FAILED"
