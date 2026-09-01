"""Case lifecycle tests: opening (`handle_payment_failed`), closing
(`handle_payment_succeeded`), escalating (`escalate`), and one diagnose ->
gate cycle (`advance_case`). `get_timeline` is a later step and still raises
NotImplementedError.

advance_case tests monkeypatch `diagnose` to return a controlled Proposal
rather than hitting an LLM (see tests/test_diagnose.py for diagnose() itself)
— the point here is the branching on the *verdict*, using the real, already-
tested policy gate.
"""

import pytest
from sqlalchemy import func, select

from app.agent.diagnose import DiagnosisFailed
from app.core.holdout import Arm
from app.db.models import Case, Outcome
from app.schemas.proposal import ActionKind, Proposal
from app.services.case_manager import (
    advance_case,
    escalate,
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
    monkeypatch.setattr("app.services.case_manager.diagnose", lambda _context: proposal)


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

    def _raise(_context):
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


def test_advance_case_does_not_touch_the_case_on_approval(db_session, monkeypatch):
    """APPROVE/REWRITE has nothing durable to do until step-06's actions
    table exists — advance_case must not claim an attempt was spent."""
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
    assert case.status == "open"
    assert case.attempts_used == attempts_before
