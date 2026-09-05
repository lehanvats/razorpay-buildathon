"""Case lifecycle tests: opening (`handle_payment_failed`), closing
(`handle_payment_succeeded`), escalating (`escalate`), one diagnose -> gate
cycle (`advance_case`), and reading it all back (`get_timeline`).

advance_case tests monkeypatch `diagnose` to return a controlled Proposal
rather than hitting an LLM (see tests/test_diagnose.py for diagnose() itself)
— the point here is the branching on the *verdict*, using the real, already-
tested policy gate.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.agent.diagnose import DiagnosisFailed
from app.core.audit import EventType
from app.core.holdout import Arm
from app.db.models import Action, AuditEvent, Case, Outcome
from app.policy.rules import MAX_CHARGE_ATTEMPTS
from app.schemas.proposal import ActionKind, Proposal
from app.services.case_manager import (
    MalformedWebhookPayload,
    advance_case,
    escalate,
    get_timeline,
    handle_payment_failed,
    handle_payment_succeeded,
)


def _event(*, order_id="order_ABC", payment_id="pay_ABC", **entity_overrides) -> dict:
    entity = {
        "id": payment_id,
        "order_id": order_id,
        "amount": 149900,
        "currency": "INR",
        "method": "upi",
        "error_code": "BAD_REQUEST_ERROR",
        "error_reason": "insufficient_funds",
        **entity_overrides,
    }
    return {"payload": {"payment": {"entity": entity}}}


def test_opens_a_case_with_taxonomy_and_arm(db_session):
    case_id = handle_payment_failed(db_session, _event())

    case = db_session.get(Case, case_id)
    assert case is not None
    assert case.razorpay_order_id == "order_ABC"
    assert case.razorpay_payment_id == "pay_ABC"
    assert case.amount_paise == 149900
    assert case.failure_class == "SOFT_FUNDS"
    assert case.arm in (Arm.TREATMENT.value, Arm.CONTROL.value)
    assert case.attempts_used == 1
    assert case.is_mandate is False


def test_control_arm_case_starts_control_observed(db_session, monkeypatch):
    monkeypatch.setattr("app.services.case_manager.assign_arm", lambda _case_id: Arm.CONTROL)
    case_id = handle_payment_failed(db_session, _event())

    case = db_session.get(Case, case_id)
    assert case.arm == Arm.CONTROL.value
    assert case.status == "control_observed"


def test_treatment_arm_case_starts_open(db_session, monkeypatch):
    monkeypatch.setattr("app.services.case_manager.assign_arm", lambda _case_id: Arm.TREATMENT)
    case_id = handle_payment_failed(db_session, _event())

    case = db_session.get(Case, case_id)
    assert case.arm == Arm.TREATMENT.value
    assert case.status == "open"


def test_repeat_failure_for_same_order_returns_existing_case(db_session):
    """Two distinct webhook deliveries (different payment ids — the customer
    retried checkout themselves) for the same order must not open a second
    case. This is a dedupe layer webhook_events.event_id cannot provide,
    since each delivery has its own event id."""
    first_id = handle_payment_failed(db_session, _event(payment_id="pay_ABC"))
    second_id = handle_payment_failed(db_session, _event(payment_id="pay_ABC_retry_2"))

    assert first_id == second_id
    assert db_session.execute(select(func.count()).select_from(Case)).scalar_one() == 1


def test_class_and_arm_are_not_recomputed_on_repeat_failure(db_session, monkeypatch):
    """failure_class and arm are written once at creation. A second delivery
    that would classify differently must not overwrite them."""
    monkeypatch.setattr("app.services.case_manager.assign_arm", lambda _case_id: Arm.CONTROL)
    handle_payment_failed(db_session, _event(payment_id="pay_1", error_reason="insufficient_funds"))
    case_id = handle_payment_failed(
        db_session, _event(payment_id="pay_2", error_reason="card_stolen_or_lost")
    )

    case = db_session.get(Case, case_id)
    assert case.failure_class == "SOFT_FUNDS"
    assert case.arm == Arm.CONTROL.value


def _paid_event(*, order_id="order_ABC", payment_id="pay_ABC", **entity_overrides) -> dict:
    entity = {
        "id": payment_id,
        "order_id": order_id,
        "amount": 149900,
        "currency": "INR",
        "method": "upi",
        **entity_overrides,
    }
    return {"payload": {"payment": {"entity": entity}}}


def test_payment_succeeded_writes_outcome_and_closes_case(db_session, monkeypatch):
    monkeypatch.setattr("app.services.case_manager.assign_arm", lambda _case_id: Arm.TREATMENT)
    case_id = handle_payment_failed(db_session, _event())

    handle_payment_succeeded(db_session, _paid_event())

    case = db_session.get(Case, case_id)
    assert case.status == "recovered"
    assert case.closed_at is not None

    outcome = db_session.get(Outcome, case_id)
    assert outcome is not None
    assert outcome.recovered_amount_paise == 149900
    assert outcome.via == "self"
    assert outcome.arm_at_recovery == Arm.TREATMENT.value


def test_payment_succeeded_is_a_noop_when_no_case_exists(db_session):
    """Most successful payments never failed first — this must not error."""
    handle_payment_succeeded(db_session, _paid_event(order_id="order_NEVER_FAILED"))

    assert db_session.execute(select(func.count()).select_from(Outcome)).scalar_one() == 0


def test_payment_succeeded_is_idempotent_across_redelivered_events(db_session):
    """payment.captured and order.paid can both fire for one recovery; the
    second delivery must not double-write or error on the existing PK."""
    handle_payment_failed(db_session, _event())

    handle_payment_succeeded(db_session, _paid_event())
    handle_payment_succeeded(db_session, _paid_event())

    assert db_session.execute(select(func.count()).select_from(Outcome)).scalar_one() == 1


def test_escalate_records_rule_id_and_reason(db_session):
    case_id = handle_payment_failed(db_session, _event())

    escalate(
        db_session, case_id, rule_id="LOW_CONFIDENCE_ESCALATE", reason="confidence 0.40 below 0.6"
    )

    case = db_session.get(Case, case_id)
    assert case.status == "escalated"
    assert case.escalated_at is not None
    assert case.escalation_rule_id == "LOW_CONFIDENCE_ESCALATE"
    assert case.escalation_reason == "confidence 0.40 below 0.6"


def test_escalate_is_a_noop_when_no_case_exists(db_session):
    escalate(db_session, "does_not_exist", rule_id="LOW_CONFIDENCE_ESCALATE", reason="n/a")

    assert db_session.execute(select(func.count()).select_from(Case)).scalar_one() == 0


def test_escalate_caps_an_oversized_reason_at_the_column_width(db_session):
    """A pydantic ValidationError listing several bad fields runs past the
    512-char `escalation_reason` column. Postgres would reject the row and the
    whole escalation would fail — leaving the case open with
    last_diagnosed_at set, so the poller never retries it and the queue never
    shows it. The column keeps a prefix; the audit event keeps the full text."""
    case_id = handle_payment_failed(db_session, _event())
    reason = "x" * 700

    escalate(db_session, case_id, rule_id="DIAGNOSIS_FAILED", reason=reason)
    db_session.flush()

    case = db_session.get(Case, case_id)
    assert case.status == "escalated"
    assert len(case.escalation_reason) == 512
    event = db_session.execute(
        select(AuditEvent).where(
            AuditEvent.case_id == case_id, AuditEvent.event_type == EventType.ESCALATED.value
        )
    ).scalar_one()
    assert event.payload_json["reason"] == reason


def test_escalate_overwrites_a_prior_escalation(db_session):
    """Re-escalating the same case (e.g. a second, unrelated stopping-rule
    hit) records the latest verdict rather than erroring on the first."""
    case_id = handle_payment_failed(db_session, _event())

    escalate(db_session, case_id, rule_id="LOW_CONFIDENCE_ESCALATE", reason="first")
    escalate(db_session, case_id, rule_id="ATTEMPT_BUDGET_EXHAUSTED", reason="second")

    case = db_session.get(Case, case_id)
    assert case.escalation_rule_id == "ATTEMPT_BUDGET_EXHAUSTED"
    assert case.escalation_reason == "second"


def _treatment_case(db_session, monkeypatch, **event_overrides) -> str:
    monkeypatch.setattr("app.services.case_manager.assign_arm", lambda _case_id: Arm.TREATMENT)
    return handle_payment_failed(db_session, _event(**event_overrides))


def _stub_diagnose(monkeypatch, proposal: Proposal) -> None:
    monkeypatch.setattr("app.services.case_manager.diagnose", lambda _context, **_kw: proposal)


def test_advance_case_refuses_a_control_case(db_session, monkeypatch):
    monkeypatch.setattr("app.services.case_manager.assign_arm", lambda _case_id: Arm.CONTROL)
    case_id = handle_payment_failed(db_session, _event())

    with pytest.raises(AssertionError):
        advance_case(db_session, case_id)


def test_advance_case_is_a_noop_for_a_terminal_status(db_session, monkeypatch):
    case_id = _treatment_case(db_session, monkeypatch)
    case = db_session.get(Case, case_id)
    case.status = "recovered"
    db_session.flush()

    def _fail_if_called(_context):
        raise AssertionError("diagnose must not run on a terminal case")

    monkeypatch.setattr("app.services.case_manager.diagnose", _fail_if_called)

    advance_case(db_session, case_id)  # must not raise, must not diagnose

    assert db_session.get(Case, case_id).status == "recovered"


def test_advance_case_escalates_when_diagnosis_fails(db_session, monkeypatch):
    case_id = _treatment_case(db_session, monkeypatch)

    def _raise(_context, **_kw):
        raise DiagnosisFailed("model never produced valid JSON")

    monkeypatch.setattr("app.services.case_manager.diagnose", _raise)

    advance_case(db_session, case_id)

    case = db_session.get(Case, case_id)
    assert case.status == "escalated"
    assert case.escalation_rule_id == "DIAGNOSIS_FAILED"
    assert "model never produced valid JSON" in case.escalation_reason


def test_advance_case_escalates_on_a_low_confidence_proposal(db_session, monkeypatch):
    case_id = _treatment_case(db_session, monkeypatch)  # SOFT_FUNDS, insufficient_funds
    _stub_diagnose(
        monkeypatch,
        Proposal(action=ActionKind.SCHEDULE_RETRY, confidence=0.4, reasoning="unsure"),
    )

    advance_case(db_session, case_id)

    case = db_session.get(Case, case_id)
    assert case.status == "escalated"
    assert case.escalation_rule_id == "LOW_CONFIDENCE_ESCALATE"


def test_advance_case_escalates_when_the_llm_itself_proposes_escalate(db_session, monkeypatch):
    case_id = _treatment_case(db_session, monkeypatch)
    _stub_diagnose(
        monkeypatch,
        Proposal(action=ActionKind.ESCALATE, confidence=0.9, reasoning="needs a human"),
    )

    advance_case(db_session, case_id)

    case = db_session.get(Case, case_id)
    assert case.status == "escalated"
    assert case.escalation_rule_id == "LLM_REQUESTED_ESCALATION"
    assert case.escalation_reason == "needs a human"


def test_advance_case_does_not_touch_the_case_on_a_blocked_proposal(db_session, monkeypatch):
    case_id = _treatment_case(
        db_session, monkeypatch, error_reason="card_stolen_or_lost"
    )  # HARD_DECLINE
    _stub_diagnose(
        monkeypatch,
        Proposal(action=ActionKind.SCHEDULE_RETRY, confidence=0.9, reasoning="retry it"),
    )
    status_before = db_session.get(Case, case_id).status

    advance_case(db_session, case_id)

    case = db_session.get(Case, case_id)
    assert case.status == status_before  # BLOCK is not an escalation
    assert case.escalation_rule_id is None


def test_advance_case_schedules_an_action_on_approval(db_session, monkeypatch):
    """APPROVE/REWRITE writes an Action row for the poller to claim and
    moves the case to "scheduled" — but must not itself claim an attempt was
    spent; that's the executor's job, at actual dispatch time."""
    case_id = _treatment_case(
        db_session, monkeypatch, error_reason="gateway_technical_error"
    )  # SOFT_TECHNICAL
    _stub_diagnose(
        monkeypatch,
        Proposal(action=ActionKind.SCHEDULE_RETRY, confidence=0.9, reasoning="retry it"),
    )
    case_before = db_session.get(Case, case_id)
    attempts_before = case_before.attempts_used

    advance_case(db_session, case_id)

    case = db_session.get(Case, case_id)
    assert case.status == "scheduled"
    assert case.attempts_used == attempts_before

    action = db_session.execute(select(Action).where(Action.case_id == case_id)).scalar_one()
    assert action.kind == ActionKind.SCHEDULE_RETRY.value
    assert action.executed_at is None
    assert action.payload_json["rule_id"] == "PASS"


def test_advance_case_marks_exhausted_on_attempt_budget_block(db_session, monkeypatch):
    """ATTEMPT_BUDGET_EXHAUSTED is the one BLOCK rule that means "stop
    permanently" (per its own docstring in policy/rules.py) — unlike other
    BLOCKs, this one gives the case a terminal exit path so it isn't left
    silently "open" forever."""
    case_id = _treatment_case(db_session, monkeypatch, error_reason="gateway_technical_error")
    case = db_session.get(Case, case_id)
    case.attempts_used = MAX_CHARGE_ATTEMPTS
    db_session.flush()
    _stub_diagnose(
        monkeypatch,
        Proposal(action=ActionKind.SCHEDULE_RETRY, confidence=0.9, reasoning="retry it"),
    )

    advance_case(db_session, case_id)

    updated = db_session.get(Case, case_id)
    assert updated.status == "exhausted"
    assert updated.escalation_rule_id is None  # exhausted, not escalated — no human queue entry


def test_advance_case_escalates_when_the_eager_pre_debit_notice_fails_to_send(
    db_session, monkeypatch
):
    """A mandate's first retry fires PreDebitNoticeExecutor eagerly inside
    schedule() (see scheduler/poller.py:schedule). If that send fails,
    scheduling the actual debit anyway would charge a customer who was never
    notified — the exact compliance breach the notice exists to prevent. The
    case must be escalated, not silently left "open" with
    last_diagnosed_at already stamped (which would make it unreachable by
    claim_new_cases forever), and no Action row should exist."""
    case_id = _treatment_case(
        db_session,
        monkeypatch,
        error_reason="gateway_technical_error",  # SOFT_TECHNICAL
        subscription_id="sub_ABC",  # is_mandate
    )
    _stub_diagnose(
        monkeypatch,
        Proposal(action=ActionKind.SCHEDULE_RETRY, confidence=0.9, reasoning="retry it"),
    )

    def _raise(*a, **kw):
        raise RuntimeError("resend 500")

    monkeypatch.setattr("app.executors.dunning.send_email", _raise)

    advance_case(db_session, case_id)

    case = db_session.get(Case, case_id)
    assert case.status == "escalated"
    assert case.escalation_rule_id == "SCHEDULING_FAILED"
    assert case.pre_debit_notice_sent_at is None
    assert (
        db_session.execute(
            select(func.count()).select_from(Action).where(Action.case_id == case_id)
        ).scalar_one()
        == 0
    )


def test_payment_succeeded_derives_via_from_the_most_recent_successful_action(db_session):
    case_id = _treatment_case_noop(db_session)
    action = Action(
        id="action_retry_1",
        case_id=case_id,
        kind=ActionKind.SCHEDULE_RETRY.value,
        verdict_rule_id="PASS",
        scheduled_for=datetime.now(UTC),
        executed_at=datetime.now(UTC),
        result=True,
        razorpay_ref="order_RETRY_NEW",
    )
    db_session.add(action)
    db_session.flush()

    handle_payment_succeeded(db_session, _paid_event())

    outcome = db_session.get(Outcome, case_id)
    assert outcome.via == "retry"


def test_payment_link_paid_falls_back_to_reference_id_when_order_id_does_not_match(db_session):
    """A payment link is its own new Order (see corrections.md #6): its
    order_id never matches cases.razorpay_order_id, so the handler must fall
    back to `payment_link.entity.reference_id`, which
    integrations.razorpay_client.create_payment_link stamps with the case
    id."""
    case_id = _treatment_case_noop(db_session)
    action = Action(
        id="action_link_1",
        case_id=case_id,
        kind=ActionKind.SEND_PAYMENT_LINK.value,
        verdict_rule_id="PASS",
        scheduled_for=datetime.now(UTC),
        executed_at=datetime.now(UTC),
        result=True,
        razorpay_ref="plink_1",
    )
    db_session.add(action)
    db_session.flush()

    event = {
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_LINK",
                    "order_id": "order_THE_LINKS_OWN_ORDER",  # deliberately not the case's order
                    "amount": 149900,
                }
            },
            "payment_link": {"entity": {"id": "plink_1", "reference_id": case_id}},
        }
    }

    handle_payment_succeeded(db_session, event)

    case = db_session.get(Case, case_id)
    assert case.status == "recovered"
    outcome = db_session.get(Outcome, case_id)
    assert outcome is not None
    assert outcome.via == "payment_link"


def test_payment_succeeded_cancels_pending_actions(db_session):
    """Charging a customer who already paid is the worst bug this system
    could ship — a self-recovery must cancel any still-pending action."""
    case_id = _treatment_case_noop(db_session)
    pending = Action(
        id="action_pending_1",
        case_id=case_id,
        kind=ActionKind.SCHEDULE_RETRY.value,
        verdict_rule_id="PASS",
        scheduled_for=datetime.now(UTC),
    )
    db_session.add(pending)
    db_session.flush()

    handle_payment_succeeded(db_session, _paid_event())

    cancelled = db_session.get(Action, "action_pending_1")
    assert cancelled.executed_at is not None
    assert cancelled.result is False


def _treatment_case_noop(db_session) -> str:
    """A treatment case whose id we control, without going through
    handle_payment_failed's assign_arm monkeypatch dance — these tests only
    care about handle_payment_succeeded's behaviour."""
    case = Case(
        id="case_via_test",
        razorpay_order_id="order_ABC",
        razorpay_payment_id="pay_ABC",
        amount_paise=149900,
        currency="INR",
        method="upi",
        is_mandate=False,
        failure_class="SOFT_FUNDS",
        arm="treatment",
        status="scheduled",
        attempts_used=1,
        messages_sent=0,
        discount_offered=False,
    )
    db_session.add(case)
    db_session.flush()
    return case.id


# --- audit trail (step-07) -------------------------------------------


def _event_types(db_session, case_id: str) -> list[str]:
    events = (
        db_session.query(AuditEvent)
        .filter_by(case_id=case_id)
        .order_by(AuditEvent.ts, AuditEvent.id)
        .all()
    )
    return [e.event_type for e in events]


def test_handle_payment_failed_writes_the_case_opening_events_in_order(db_session):
    case_id = handle_payment_failed(db_session, _event())

    assert _event_types(db_session, case_id) == [
        EventType.WEBHOOK_RECEIVED.value,
        EventType.CASE_OPENED.value,
        EventType.ARM_ASSIGNED.value,
        EventType.CLASSIFIED.value,
    ]


def test_handle_payment_failed_writes_no_events_on_a_repeat_delivery(db_session):
    """A second payment.failed for an order that already has a case returns
    the existing id and does nothing else -- including on the audit trail."""
    first_id = handle_payment_failed(db_session, _event(payment_id="pay_ABC"))
    handle_payment_failed(db_session, _event(payment_id="pay_ABC_retry_2"))

    assert len(_event_types(db_session, first_id)) == 4


def test_handle_payment_failed_raises_on_a_missing_order_id(db_session):
    """The graceful-failure path: a malformed-but-signature-valid payload
    must not 500 (see api/routes/webhooks.py and corrections.md #1) -- this
    tests only the exception `handle_payment_failed` itself raises."""
    bad_event = {"payload": {"payment": {"entity": {"id": "pay_MALFORMED"}}}}

    with pytest.raises(MalformedWebhookPayload):
        handle_payment_failed(db_session, bad_event)

    assert db_session.execute(select(func.count()).select_from(Case)).scalar_one() == 0


def test_advance_case_writes_llm_proposed_on_a_successful_diagnosis(db_session, monkeypatch):
    case_id = _treatment_case(db_session, monkeypatch)
    _stub_diagnose(
        monkeypatch,
        Proposal(action=ActionKind.SCHEDULE_RETRY, confidence=0.9, reasoning="clear case"),
    )

    advance_case(db_session, case_id)

    events = _event_types(db_session, case_id)
    assert EventType.LLM_PROPOSED.value in events
    proposed = next(
        e
        for e in db_session.query(AuditEvent).filter_by(case_id=case_id)
        if e.event_type == EventType.LLM_PROPOSED.value
    )
    assert proposed.payload_json == {"reasoning": "clear case"}


def test_advance_case_writes_llm_rejected_when_diagnosis_fails(db_session, monkeypatch):
    case_id = _treatment_case(db_session, monkeypatch)

    def _raise(_context, **_kw):
        raise DiagnosisFailed("both providers unavailable")

    monkeypatch.setattr("app.services.case_manager.diagnose", _raise)

    advance_case(db_session, case_id)

    assert EventType.LLM_REJECTED.value in _event_types(db_session, case_id)
    assert EventType.ESCALATED.value in _event_types(db_session, case_id)


def test_advance_case_writes_policy_blocked_on_a_blocked_proposal(db_session, monkeypatch):
    case_id = _treatment_case(
        db_session, monkeypatch, error_reason="card_stolen_or_lost"
    )  # HARD_DECLINE
    _stub_diagnose(
        monkeypatch,
        Proposal(action=ActionKind.SCHEDULE_RETRY, confidence=0.9, reasoning="retry it"),
    )

    advance_case(db_session, case_id)

    events = list(db_session.query(AuditEvent).filter_by(case_id=case_id))
    blocked = next(e for e in events if e.event_type == EventType.POLICY_BLOCKED.value)
    assert blocked.payload_json["rule_id"] == "HARD_DECLINE_BLOCK"


def test_advance_case_writes_policy_approved_on_approval(db_session, monkeypatch):
    case_id = _treatment_case(
        db_session, monkeypatch, error_reason="gateway_technical_error"
    )  # SOFT_TECHNICAL
    _stub_diagnose(
        monkeypatch,
        Proposal(action=ActionKind.SCHEDULE_RETRY, confidence=0.9, reasoning="retry it"),
    )

    advance_case(db_session, case_id)

    events = list(db_session.query(AuditEvent).filter_by(case_id=case_id))
    approved = next(e for e in events if e.event_type == EventType.POLICY_APPROVED.value)
    assert approved.payload_json["rule_id"] == "PASS"


def test_escalate_writes_an_escalated_event(db_session):
    case_id = _treatment_case_noop(db_session)

    escalate(db_session, case_id, rule_id="LOW_CONFIDENCE_ESCALATE", reason="unsure")

    event = db_session.query(AuditEvent).filter_by(case_id=case_id).one()
    assert event.event_type == EventType.ESCALATED.value
    assert event.payload_json == {"rule_id": "LOW_CONFIDENCE_ESCALATE", "reason": "unsure"}


def test_payment_succeeded_writes_a_recovered_event(db_session):
    case_id = _treatment_case_noop(db_session)

    handle_payment_succeeded(db_session, _paid_event())

    event = db_session.query(AuditEvent).filter_by(case_id=case_id).one()
    assert event.event_type == EventType.RECOVERED.value
    assert event.payload_json == {"amount_paise": 149900}


def test_get_timeline_orders_by_ts_then_id_and_extracts_rule_id(db_session):
    """Several events land in one transaction with an identical `ts`
    (Postgres's server_default is the transaction timestamp, not the wall
    clock) -- `id`'s insertion-ordered sequence, not `ts` alone, is what
    keeps this in true chronological order. See db/models.py:AuditEvent."""
    case_id = handle_payment_failed(db_session, _event())

    timeline = get_timeline(db_session, case_id)

    assert [entry["event_type"] for entry in timeline] == [
        EventType.WEBHOOK_RECEIVED.value,
        EventType.CASE_OPENED.value,
        EventType.ARM_ASSIGNED.value,
        EventType.CLASSIFIED.value,
    ]
    classified = timeline[-1]
    assert classified["payload"] == {"failure_class": "SOFT_FUNDS"}
    assert classified["rule_id"] is None  # only policy events carry rule_id


def test_get_timeline_is_empty_for_a_case_with_no_events(db_session):
    case_id = _treatment_case_noop(db_session)
    assert get_timeline(db_session, case_id) == []
