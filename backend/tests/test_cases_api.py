"""GET /api/cases and GET /api/cases/{case_id} — list + case-detail/timeline.

Deliberately end-to-end through the real routes rather than unit tests of
the underlying query functions — these are what actually prove the audit
trail and the list filters work, not a component test.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db.models import Case, Outcome

URL = "/api/cases"


def _make_case(db_session, **overrides) -> Case:
    defaults = dict(
        id="case_api_test",
        razorpay_order_id="order_API",
        razorpay_payment_id="pay_API",
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


def test_list_cases_returns_every_case_newest_first(client, db_session):
    # Explicit, distinct created_at: server_default=func.now() is the
    # *transaction* timestamp (same pitfall as audit_events.ts), so two rows
    # inserted in one test transaction would otherwise tie.
    _make_case(
        db_session,
        id="c_older",
        razorpay_order_id="order_older",
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    _make_case(
        db_session,
        id="c_newer",
        razorpay_order_id="order_newer",
        created_at=datetime(2026, 9, 2, tzinfo=UTC),
    )
    db_session.commit()

    body = client.get(URL).json()
    assert [c["id"] for c in body] == ["c_newer", "c_older"]


def test_list_cases_filters_by_arm_status_and_failure_class(client, db_session):
    _make_case(
        db_session, id="c1", razorpay_order_id="o1", arm="treatment", failure_class="SOFT_FUNDS"
    )
    _make_case(
        db_session,
        id="c2",
        razorpay_order_id="o2",
        arm="control",
        status="control_observed",
        failure_class="DROPOFF",
    )
    db_session.commit()

    assert [c["id"] for c in client.get(URL, params={"arm": "control"}).json()] == ["c2"]
    assert [c["id"] for c in client.get(URL, params={"failure_class": "SOFT_FUNDS"}).json()] == [
        "c1"
    ]
    assert [c["id"] for c in client.get(URL, params={"status": "open"}).json()] == ["c1"]


def test_get_case_returns_404_for_an_unknown_id(client):
    response = client.get(f"{URL}/case_does_not_exist")
    assert response.status_code == 404


def test_get_case_returns_case_fields_and_empty_timeline(client, db_session):
    case = _make_case(db_session)

    response = client.get(f"{URL}/{case.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == case.id
    assert body["orderId"] == "order_API"
    assert body["amountPaise"] == 149_900
    assert body["failureClass"] == "SOFT_TECHNICAL"
    assert body["arm"] == "treatment"
    assert body["recoveredAmountPaise"] is None
    assert body["timeline"] == []


def test_get_case_includes_the_recovered_amount_once_an_outcome_exists(client, db_session):
    case = _make_case(db_session, status="recovered")
    db_session.add(
        Outcome(
            case_id=case.id,
            recovered_amount_paise=149_900,
            recovered_at=func.now(),
            via="retry",
            arm_at_recovery="treatment",
        )
    )
    db_session.flush()

    response = client.get(f"{URL}/{case.id}")

    assert response.status_code == 200
    assert response.json()["recoveredAmountPaise"] == 149_900


def test_get_case_renders_the_full_ordered_timeline_via_the_real_webhook_flow(client, db_session):
    """Post a real payment.failed through the webhook route rather than
    hand-building AuditEvent rows -- this is what actually proves the
    end-to-end wiring (webhooks -> case_manager -> audit -> this route).
    Arm assignment is left to the real holdout: WEBHOOK_RECEIVED/
    CASE_OPENED/ARM_ASSIGNED/CLASSIFIED fire unconditionally either way."""
    from app.integrations.razorpay_client import sign_payload
    from tests.conftest import TEST_WEBHOOK_SECRET

    raw = (
        b'{"event": "payment.failed", "payload": {"payment": {"entity": '
        b'{"id": "pay_TIMELINE", "order_id": "order_TIMELINE", "amount": 99900,'
        b' "currency": "INR", "method": "upi", "error_reason": "insufficient_funds"'
        b"}}}}"
    )
    response = client.post(
        "/api/webhooks/razorpay",
        content=raw,
        headers={
            "X-Razorpay-Signature": sign_payload(raw, TEST_WEBHOOK_SECRET),
            "X-Razorpay-Event-Id": "evt_TIMELINE",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    case_id = db_session.execute(
        select(Case.id).where(Case.razorpay_order_id == "order_TIMELINE")
    ).scalar_one()

    detail = client.get(f"{URL}/{case_id}").json()

    event_types = [entry["eventType"] for entry in detail["timeline"]]
    assert event_types == ["webhook_received", "case_opened", "arm_assigned", "classified"]
    # ts non-decreasing and never reordered — the (ts, id) tiebreak holds.
    assert [entry["ts"] for entry in detail["timeline"]] == sorted(
        entry["ts"] for entry in detail["timeline"]
    )
