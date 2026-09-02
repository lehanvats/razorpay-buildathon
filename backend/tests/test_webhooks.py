"""Webhook ingress tests — signature verification and idempotency."""

import json

from sqlalchemy import func, select

from app.db.models import Case, Outcome, WebhookEvent
from app.integrations.razorpay_client import sign_payload
from tests.conftest import TEST_WEBHOOK_SECRET

URL = "/api/webhooks/razorpay"

# Deliberately NOT canonical JSON: irregular spacing, and keys in an order
# `json.dumps` would not reproduce. An implementation that verifies against a
# re-serialised dict fails on this body — which is the whole point of it.
RAW_PAYMENT_FAILED = (
    b'{"event": "payment.failed",   "account_id": "acc_TEST",\n'
    b'  "contains": ["payment"],\n'
    b'  "payload": {"payment": {"entity": {"id": "pay_TEST0001",'
    b' "order_id": "order_TEST0001", "amount": 149900, "currency": "INR",'
    b' "method": "upi", "error_code": "BAD_REQUEST_ERROR",'
    b' "error_reason": "insufficient_funds"}}},\n'
    b'  "created_at": 1756684800}'
)


def _headers(raw: bytes, *, event_id: str = "evt_TEST0001", signature: str | None = None):
    return {
        "X-Razorpay-Signature": signature
        if signature is not None
        else sign_payload(raw, TEST_WEBHOOK_SECRET),
        "X-Razorpay-Event-Id": event_id,
        "Content-Type": "application/json",
    }


def _row_count(db) -> int:
    return db.execute(select(func.count()).select_from(WebhookEvent)).scalar_one()


def test_valid_signature_accepted(client, db_session):
    """HMAC-SHA256 over the raw body with the webhook secret."""
    response = client.post(URL, content=RAW_PAYMENT_FAILED, headers=_headers(RAW_PAYMENT_FAILED))

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert _row_count(db_session) == 1


def test_invalid_signature_rejected_with_400(client, db_session):
    """And no case is opened."""
    response = client.post(
        URL,
        content=RAW_PAYMENT_FAILED,
        headers=_headers(RAW_PAYMENT_FAILED, signature="deadbeef" * 8),
    )

    assert response.status_code == 400
    # Nothing is persisted from an unverified body — otherwise an
    # unauthenticated caller could fill the table at will.
    assert _row_count(db_session) == 0


def test_missing_signature_header_rejected(client, db_session):
    """An absent header is a rejection, never a skipped check."""
    response = client.post(
        URL, content=RAW_PAYMENT_FAILED, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 400
    assert _row_count(db_session) == 0


def test_signature_computed_over_raw_bytes_not_reserialised_json(client, db_session):
    """Send a body with unusual key order / whitespace and confirm it still
    verifies. Re-serialising a parsed dict changes the digest — this is the
    classic way webhook auth breaks in production.
    """
    # Guard against a vacuous test: if the body were already canonical, both
    # signatures would match and the assertions below would prove nothing.
    reserialised = json.dumps(json.loads(RAW_PAYMENT_FAILED)).encode()
    assert reserialised != RAW_PAYMENT_FAILED

    over_raw = sign_payload(RAW_PAYMENT_FAILED, TEST_WEBHOOK_SECRET)
    over_reserialised = sign_payload(reserialised, TEST_WEBHOOK_SECRET)
    assert over_raw != over_reserialised

    accepted = client.post(
        URL, content=RAW_PAYMENT_FAILED, headers=_headers(RAW_PAYMENT_FAILED, signature=over_raw)
    )
    assert accepted.status_code == 200

    rejected = client.post(
        URL,
        content=RAW_PAYMENT_FAILED,
        headers=_headers(RAW_PAYMENT_FAILED, event_id="evt_TEST0002", signature=over_reserialised),
    )
    assert rejected.status_code == 400
    assert _row_count(db_session) == 1


def test_duplicate_event_id_is_a_noop(client, db_session):
    """Razorpay redelivers. A duplicate must not open a second case or fire
    a second retry at a customer."""
    headers = _headers(RAW_PAYMENT_FAILED)

    first = client.post(URL, content=RAW_PAYMENT_FAILED, headers=headers)
    second = client.post(URL, content=RAW_PAYMENT_FAILED, headers=headers)

    assert first.json()["status"] == "accepted"
    # 200, not 409 — a non-2xx makes Razorpay redeliver harder, and there is
    # nothing on its side to fix.
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert _row_count(db_session) == 1


def test_duplicate_detected_without_the_event_id_header(client, db_session):
    """The seeder posts synthetic webhooks with no event-id header; identical
    bodies must still dedupe on the body digest."""
    headers = {
        "X-Razorpay-Signature": sign_payload(RAW_PAYMENT_FAILED, TEST_WEBHOOK_SECRET),
        "Content-Type": "application/json",
    }

    client.post(URL, content=RAW_PAYMENT_FAILED, headers=headers)
    second = client.post(URL, content=RAW_PAYMENT_FAILED, headers=headers)

    assert second.json()["status"] == "duplicate"
    assert _row_count(db_session) == 1


def test_raw_payload_stored_before_processing(client, db_session):
    """A crash mid-processing must leave a replayable record."""
    client.post(URL, content=RAW_PAYMENT_FAILED, headers=_headers(RAW_PAYMENT_FAILED))

    event = db_session.execute(select(WebhookEvent)).scalar_one()
    assert event.event_id == "evt_TEST0001"
    assert event.event_type == "payment.failed"
    assert event.signature_valid is True
    assert event.received_at is not None
    # Stamped once the case manager claims it — the marker that makes an
    # interrupted delivery (a crash between insert and dispatch) replayable
    # rather than lost.
    assert event.processed_at is not None
    # Stored verbatim, not summarised: the payload is the audit record.
    assert event.payload_json == json.loads(RAW_PAYMENT_FAILED)


def test_payment_failed_opens_a_case(client, db_session):
    """The webhook route dispatches to the case manager, not just storage."""
    response = client.post(URL, content=RAW_PAYMENT_FAILED, headers=_headers(RAW_PAYMENT_FAILED))
    assert response.status_code == 200

    case = db_session.execute(select(Case)).scalar_one()
    assert case.razorpay_order_id == "order_TEST0001"
    assert case.amount_paise == 149900
    assert case.failure_class == "SOFT_FUNDS"  # error_reason: insufficient_funds


RAW_PAYMENT_CAPTURED = (
    b'{"event": "payment.captured", "account_id": "acc_TEST",\n'
    b'  "contains": ["payment"],\n'
    b'  "payload": {"payment": {"entity": {"id": "pay_TEST0001",'
    b' "order_id": "order_TEST0001", "amount": 149900, "currency": "INR",'
    b' "method": "upi"}}},\n'
    b'  "created_at": 1756684900}'
)


def test_payment_captured_closes_the_case_it_recovered(client, db_session):
    """The full loop: a failure opens a case, a later capture closes it with
    an outcome row — end to end through the route, not just the unit."""
    client.post(URL, content=RAW_PAYMENT_FAILED, headers=_headers(RAW_PAYMENT_FAILED))
    case_id = db_session.execute(select(Case)).scalar_one().id

    response = client.post(
        URL,
        content=RAW_PAYMENT_CAPTURED,
        headers=_headers(RAW_PAYMENT_CAPTURED, event_id="evt_TEST0002"),
    )
    assert response.status_code == 200

    case = db_session.get(Case, case_id)
    assert case.status == "recovered"
    outcome = db_session.get(Outcome, case_id)
    assert outcome is not None
    assert outcome.recovered_amount_paise == 149900


RAW_ORDER_PAID = (
    b'{"event": "order.paid", "account_id": "acc_TEST",\n'
    b'  "contains": ["payment", "order"],\n'
    b'  "payload": {'
    b'"payment": {"entity": {"id": "pay_TEST0001",'
    b' "order_id": "order_TEST0001", "amount": 149900, "currency": "INR",'
    b' "method": "upi"}},'
    b'"order": {"entity": {"id": "order_TEST0001", "amount": 149900,'
    b' "amount_paid": 149900, "status": "paid"}}'
    b"},\n"
    b'  "created_at": 1756684950}'
)

RAW_PAYMENT_LINK_PAID = (
    b'{"event": "payment_link.paid", "account_id": "acc_TEST",\n'
    b'  "contains": ["payment_link", "payment", "order"],\n'
    b'  "payload": {'
    b'"payment": {"entity": {"id": "pay_TEST0001",'
    b' "order_id": "order_TEST0001", "amount": 149900, "currency": "INR",'
    b' "method": "upi"}},'
    b'"payment_link": {"entity": {"id": "plink_TEST0001", "status": "paid"}}'
    b"},\n"
    b'  "created_at": 1756684975}'
)


def test_order_paid_closes_the_case_it_recovered(client, db_session):
    """`order.paid` carries both an order and a payment entity — confirms
    the handler reads the payment entity correctly in this shape too, not
    just payment.captured's."""
    client.post(URL, content=RAW_PAYMENT_FAILED, headers=_headers(RAW_PAYMENT_FAILED))
    case_id = db_session.execute(select(Case)).scalar_one().id

    response = client.post(
        URL, content=RAW_ORDER_PAID, headers=_headers(RAW_ORDER_PAID, event_id="evt_TEST0004")
    )
    assert response.status_code == 200
    assert db_session.get(Case, case_id).status == "recovered"
    assert db_session.get(Outcome, case_id) is not None


def test_payment_link_paid_closes_the_case_it_recovered(client, db_session):
    client.post(URL, content=RAW_PAYMENT_FAILED, headers=_headers(RAW_PAYMENT_FAILED))
    case_id = db_session.execute(select(Case)).scalar_one().id

    response = client.post(
        URL,
        content=RAW_PAYMENT_LINK_PAID,
        headers=_headers(RAW_PAYMENT_LINK_PAID, event_id="evt_TEST0005"),
    )
    assert response.status_code == 200
    assert db_session.get(Case, case_id).status == "recovered"
    assert db_session.get(Outcome, case_id) is not None


def test_payment_link_paid_falls_back_to_reference_id_when_order_id_differs(client, db_session):
    """A payment link is its own new Razorpay Order (corrections.md #6): its
    order_id never matches the case's original razorpay_order_id, so the
    route must still close the loop via `payment_link.entity.reference_id`."""
    client.post(URL, content=RAW_PAYMENT_FAILED, headers=_headers(RAW_PAYMENT_FAILED))
    case_id = db_session.execute(select(Case)).scalar_one().id

    raw = (
        b'{"event": "payment_link.paid", "account_id": "acc_TEST",\n'
        b'  "contains": ["payment_link", "payment", "order"],\n'
        b'  "payload": {'
        b'"payment": {"entity": {"id": "pay_TEST_LINK",'
        b' "order_id": "order_THE_LINKS_OWN_ORDER", "amount": 149900,'
        b' "currency": "INR", "method": "upi"}},'
        b'"payment_link": {"entity": {"id": "plink_TEST0002", "status": "paid",'
        + f'"reference_id": "{case_id}"'.encode()
        + b"}}"
        b"},\n"
        b'  "created_at": 1756685000}'
    )

    response = client.post(URL, content=raw, headers=_headers(raw, event_id="evt_TEST0006"))

    assert response.status_code == 200
    assert db_session.get(Case, case_id).status == "recovered"
    assert db_session.get(Outcome, case_id) is not None


def test_payment_captured_for_an_order_with_no_case_is_a_noop(client, db_session):
    """A payment that succeeded on the first try never opened a case — the
    capture event must not error just because there's nothing to close."""
    response = client.post(
        URL,
        content=RAW_PAYMENT_CAPTURED,
        headers=_headers(RAW_PAYMENT_CAPTURED, event_id="evt_TEST0003"),
    )
    assert response.status_code == 200
    assert db_session.execute(select(func.count()).select_from(Outcome)).scalar_one() == 0


def test_duplicate_payment_failed_does_not_open_a_second_case(client, db_session):
    """Redelivery is a no-op at the webhook_events layer already; this
    confirms the case layer would also survive a second, distinct delivery
    for the same order (see test_case_manager.py for the direct unit test)."""
    headers = _headers(RAW_PAYMENT_FAILED)
    client.post(URL, content=RAW_PAYMENT_FAILED, headers=headers)
    client.post(URL, content=RAW_PAYMENT_FAILED, headers=headers)  # duplicate event_id

    assert db_session.execute(select(func.count()).select_from(Case)).scalar_one() == 1


def test_malformed_json_rejected_after_signature_passes(client, db_session):
    """A correctly signed body that is not JSON is still a 400, not a 500."""
    raw = b"not json at all"
    response = client.post(URL, content=raw, headers=_headers(raw))

    assert response.status_code == 400
    assert _row_count(db_session) == 0


def test_malformed_payment_failed_entity_is_rejected_gracefully_not_500(client, db_session):
    """corrections.md #1: a correctly-signed payment.failed whose entity is
    missing order_id must not 500 -- that would make every Razorpay
    redelivery hit the identical crash forever. The raw payload is still
    durably stored (replayable if the code changes), but processed_at stays
    NULL: `handle_payment_failed` never actually handled it."""
    raw = (
        b'{"event": "payment.failed", "payload": {"payment": {"entity": {"id": "pay_MALFORMED"}}}}'
    )
    response = client.post(URL, content=raw, headers=_headers(raw, event_id="evt_MALFORMED"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"

    row = db_session.execute(
        select(WebhookEvent).where(WebhookEvent.event_id == "evt_MALFORMED")
    ).scalar_one()
    assert row.processed_at is None
    assert db_session.execute(select(func.count()).select_from(Case)).scalar_one() == 0
