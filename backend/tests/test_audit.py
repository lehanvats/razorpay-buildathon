"""core/audit.py tests: `record()` writes an append-only AuditEvent row.

Every call site (case_manager, executors/base, scheduler/poller) is
exercised in its own test file with its own fixtures — this file tests
`record()` in isolation: what it persists, and what it defaults.
"""

from app.core.audit import Actor, EventType, record
from app.db.models import AuditEvent, Case


def _make_case(db_session, **overrides) -> Case:
    defaults = dict(
        id="case_audit_test",
        razorpay_order_id="order_AUDIT",
        razorpay_payment_id="pay_AUDIT",
        amount_paise=100_000,
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


def test_record_writes_actor_event_type_and_payload(db_session):
    case = _make_case(db_session)

    record(
        db_session,
        case_id=case.id,
        actor=Actor.POLICY,
        event_type=EventType.CLASSIFIED,
        payload={"failure_class": "SOFT_TECHNICAL"},
    )

    event = db_session.query(AuditEvent).filter_by(case_id=case.id).one()
    assert event.actor == Actor.POLICY.value
    assert event.event_type == EventType.CLASSIFIED.value
    assert event.payload_json == {"failure_class": "SOFT_TECHNICAL"}
    assert event.ts is not None


def test_record_defaults_a_missing_payload_to_an_empty_dict(db_session):
    """`AuditEvent.payload_json` is NOT NULL and `TimelineEntry.payload` is a
    required field with no default -- a stored NULL would surface as a
    Pydantic validation error at the API boundary rather than at the write."""
    case = _make_case(db_session)

    record(db_session, case_id=case.id, actor=Actor.WEBHOOK, event_type=EventType.WEBHOOK_RECEIVED)

    event = db_session.query(AuditEvent).filter_by(case_id=case.id).one()
    assert event.payload_json == {}


def test_no_update_or_delete_path_exists():
    """Append-only is enforced by the absence of code, not a comment."""
    import app.core.audit as audit_module

    assert not hasattr(audit_module, "update_event")
    assert not hasattr(audit_module, "delete_event")
