"""GET /api/dashboard end-to-end."""

from datetime import UTC, datetime

from app.db.models import Case, Outcome


def _case(db_session, id: str, *, arm: str, failure_class: str) -> Case:
    case = Case(
        id=id,
        razorpay_order_id=f"order_{id}",
        razorpay_payment_id=f"pay_{id}",
        amount_paise=100_000,
        currency="INR",
        method="card",
        is_mandate=False,
        failure_class=failure_class,
        arm=arm,
        status="open",
        attempts_used=1,
        messages_sent=0,
        discount_offered=False,
    )
    db_session.add(case)
    db_session.flush()
    return case


def test_dashboard_returns_funnel_and_arm_split(client, db_session):
    t = _case(db_session, "c1", arm="treatment", failure_class="SOFT_FUNDS")
    _case(db_session, "c2", arm="control", failure_class="SOFT_FUNDS")
    db_session.add(
        Outcome(
            case_id=t.id,
            recovered_amount_paise=100_000,
            recovered_at=datetime(2026, 9, 2, tzinfo=UTC),
            via="retry",
            arm_at_recovery="treatment",
        )
    )
    db_session.commit()

    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["funnel"]["failed"] == 2
    assert body["treatment"]["cases"] == 1
    assert body["control"]["cases"] == 1
    assert body["grossRecoveredPaise"] == 100_000
    assert "SOFT_FUNDS" in body["byFailureClass"]


def test_dashboard_on_an_empty_database_is_all_zeros(client, db_session):
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["funnel"] == {"failed": 0, "eligible": 0, "treated": 0, "recovered": 0}
    assert body["grossRecoveredPaise"] == 0
    assert body["incrementalRecoveredPaise"] == 0
