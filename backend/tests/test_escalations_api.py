"""GET /api/escalations and POST /api/escalations/{id}/resolve."""

from datetime import UTC, datetime

from app.core.audit import Actor, EventType
from app.core.audit import record as audit_record
from app.db.models import Case


def _escalated_case(db_session, id: str = "case_esc") -> Case:
    case = Case(
        id=id,
        razorpay_order_id=f"order_{id}",
        razorpay_payment_id=f"pay_{id}",
        amount_paise=250_000,
        currency="INR",
        method="card",
        is_mandate=False,
        failure_class="HARD_DECLINE",
        arm="treatment",
        status="escalated",
        attempts_used=1,
        messages_sent=0,
        discount_offered=False,
        escalated_at=datetime(2026, 9, 2, 10, 0, tzinfo=UTC),
        escalation_rule_id="HARD_DECLINE_BLOCK",
        escalation_reason="Unrecoverable card decline.",
    )
    db_session.add(case)
    db_session.commit()
    return case


def test_list_escalations_returns_the_open_ones(client, db_session):
    _escalated_case(db_session)

    resp = client.get("/api/escalations")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["ruleId"] == "HARD_DECLINE_BLOCK"
    assert body[0]["blockedDecision"] == "ESCALATE"
    assert body[0]["case"]["id"] == "case_esc"


def test_list_escalations_excludes_already_resolved_cases(client, db_session):
    case = _escalated_case(db_session)
    audit_record(
        db_session,
        case_id=case.id,
        actor=Actor.HUMAN,
        event_type=EventType.ESCALATION_RESOLVED,
        payload={"note": "handled offline"},
    )
    db_session.commit()

    resp = client.get("/api/escalations")
    assert resp.json() == []


def test_resolve_writes_a_human_audit_event_and_does_not_change_status(client, db_session):
    case = _escalated_case(db_session)

    resp = client.post(f"/api/escalations/{case.id}/resolve", json={"note": "refunded manually"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"

    db_session.refresh(case)
    assert case.status == "escalated"  # resolving does not resume the agent

    resp2 = client.get("/api/escalations")
    assert resp2.json() == []  # now filtered out as resolved


def test_resolve_returns_404_for_an_unknown_case(client, db_session):
    resp = client.post("/api/escalations/does-not-exist/resolve", json={"note": "x"})
    assert resp.status_code == 404
