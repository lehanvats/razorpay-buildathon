"""GET /api/cases/{case_id} — the case-detail + timeline route.

Deliberately end-to-end through the real route (not just a unit test of
get_timeline()): CaseDetailPage.tsx/CaseTimeline.tsx are deferred to step-08
(the app shell/routing/fetch-client stubs they'd need are all TODO(step-08)
themselves — see corrections.md), so this route is what actually proves the
audit trail works, not a component test.
"""

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


def test_get_case_returns_404_for_an_unknown_id(client):
    response = client.get(f"{URL}/case_does_not_exist")
    assert response.status_code == 404


def test_get_case_returns_case_fields_and_empty_timeline(client, db_session):
    case = _make_case(db_session)

    response = client.get(f"{URL}/{case.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == case.id
    assert body["order_id"] == "order_API"
    assert body["amount_paise"] == 149_900
    assert body["failure_class"] == "SOFT_TECHNICAL"
    assert body["arm"] == "treatment"
    assert body["recovered_amount_paise"] is None
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
    assert response.json()["recovered_amount_paise"] == 149_900


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

    event_types = [entry["event_type"] for entry in detail["timeline"]]
    assert event_types == ["webhook_received", "case_opened", "arm_assigned", "classified"]
    # ts non-decreasing and never reordered — the (ts, id) tiebreak holds.
    assert [entry["ts"] for entry in detail["timeline"]] == sorted(
        entry["ts"] for entry in detail["timeline"]
    )
