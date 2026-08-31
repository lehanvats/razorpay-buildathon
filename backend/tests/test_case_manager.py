"""Case creation tests.

Only `handle_payment_failed` is exercised — `advance_case`,
`handle_payment_succeeded`, `escalate` and `get_timeline` are later steps and
still raise NotImplementedError.
"""

from sqlalchemy import func, select

from app.core.holdout import Arm
from app.db.models import Case
from app.services.case_manager import handle_payment_failed


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
