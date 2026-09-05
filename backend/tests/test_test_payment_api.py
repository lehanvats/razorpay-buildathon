"""POST /api/test-payment and /reconcile — the operator-initiated real payment.

Razorpay is never called: `create_payment_link` is patched where the
executor imports it (matching tests/test_executors.py), `fetch_payment_link`
where services/test_payment.py imports it, and `send_email` in the dunning
executor. What is NOT patched is the gate, the scheduler's `schedule` /
`dispatch`, or `handle_payment_failed` / `handle_payment_succeeded` — the
point of these tests is that the test-payment flow runs the real loop.
"""

from hashlib import sha256
from hmac import new as hmac_new

import pytest
from sqlalchemy import select

from app.core.audit import EventType
from app.db.models import Action, AuditEvent, Case, Outcome
from app.integrations.razorpay_client import (
    payment_link_callback_message,
    verify_payment_link_callback_signature,
)

URL = "/api/test-payment"
KEY_SECRET = "test_key_secret"


@pytest.fixture
def razorpay_stub(monkeypatch):
    """Patch every outbound call the flow makes; return the captured link."""
    created: dict = {}

    def _create(amount_paise, email, **notes):
        created.update(amount_paise=amount_paise, email=email, case_id=notes.get("case_id"))
        return {"id": "plink_TEST1", "short_url": "https://rzp.io/i/testlink"}

    monkeypatch.setattr("app.executors.payment_link.create_payment_link", _create)
    monkeypatch.setattr("app.executors.dunning.send_email", lambda *a, **kw: "dry-run:test")
    monkeypatch.setattr("app.services.test_payment.settings.razorpay_key_secret", KEY_SECRET)
    return created


def _events(db, case_id):
    return [
        e.event_type
        for e in db.execute(
            select(AuditEvent)
            .where(AuditEvent.case_id == case_id)
            .order_by(AuditEvent.ts, AuditEvent.id)
        ).scalars()
    ]


def _paid_link(case_id: str, amount: int = 49_900) -> dict:
    return {
        "id": "plink_TEST1",
        "status": "paid",
        "amount": amount,
        "amount_paid": amount,
        "currency": "INR",
        "reference_id": case_id,
        "order_id": "order_THE_LINKS_OWN_ORDER",
        "short_url": "https://rzp.io/i/testlink",
        "payments": [{"payment_id": "pay_REAL1", "amount": amount, "method": "upi"}],
    }


def _signature(link_id, ref, status, payment_id, secret=KEY_SECRET) -> str:
    return hmac_new(
        secret.encode(), payment_link_callback_message(link_id, ref, status, payment_id), sha256
    ).hexdigest()


# --- create ------------------------------------------------------------


def test_create_runs_the_real_loop_and_returns_the_link(client, db_session, razorpay_stub):
    resp = client.post(URL, json={"amountPaise": 49_900, "customerEmail": "payer@example.com"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["paymentUrl"] == "https://rzp.io/i/testlink"
    assert body["paymentLinkId"] == "plink_TEST1"
    assert body["amountPaise"] == 49_900
    assert body["status"] == "awaiting_customer"

    case = db_session.get(Case, body["caseId"])
    assert case is not None
    assert case.arm == "treatment"  # a control case would never get a link
    assert case.failure_class == "DROPOFF"
    assert case.status == "awaiting_customer"
    assert case.last_diagnosed_at is not None  # invisible to claim_new_cases
    assert case.customer_email == "payer@example.com"

    # The executor received the case id for the link's reference_id.
    assert razorpay_stub == {
        "amount_paise": 49_900,
        "email": "payer@example.com",
        "case_id": case.id,
    }

    action = db_session.execute(select(Action).where(Action.case_id == case.id)).scalar_one()
    assert action.kind == "SEND_PAYMENT_LINK"
    assert action.result is True
    assert action.razorpay_ref == "plink_TEST1"
    assert action.executed_at is not None

    # The trail reads like a poller-driven case, with the operator named in
    # the proposer's seat — and OPERATOR_PROPOSED, never LLM_PROPOSED.
    events = _events(db_session, case.id)
    assert events == [
        EventType.WEBHOOK_RECEIVED,
        EventType.CASE_OPENED,
        EventType.ARM_ASSIGNED,
        EventType.CLASSIFIED,
        EventType.OPERATOR_PROPOSED,
        EventType.ACTION_SCHEDULED,
        EventType.POLICY_APPROVED,
        EventType.ACTION_STARTED,  # payment link
        EventType.ACTION_COMPLETED,
        EventType.ACTION_STARTED,  # dunning email
        EventType.ACTION_COMPLETED,
    ]
    assert EventType.LLM_PROPOSED not in events


def test_create_surfaces_an_executor_failure_with_the_case_id(client, db_session, monkeypatch):
    def _raise(*a, **kw):
        raise RuntimeError("razorpay 500")

    monkeypatch.setattr("app.executors.payment_link.create_payment_link", _raise)
    monkeypatch.setattr("app.executors.dunning.send_email", lambda *a, **kw: "dry-run:test")

    resp = client.post(URL, json={"amountPaise": 49_900, "customerEmail": "payer@example.com"})
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "razorpay 500" in detail["message"]

    # The case was committed with the failure on its trail, not rolled back.
    case = db_session.get(Case, detail["caseId"])
    assert case is not None
    assert EventType.ACTION_FAILED in _events(db_session, case.id)


def test_create_validates_amount_and_email(client, db_session, razorpay_stub):
    assert client.post(URL, json={"amountPaise": 50, "customerEmail": "a@b.co"}).status_code == 422
    assert (
        client.post(URL, json={"amountPaise": 49_900, "customerEmail": "not-an-email"}).status_code
        == 422
    )


def test_test_payment_routes_404_when_demo_mode_is_disabled(client, db_session, monkeypatch):
    monkeypatch.setattr("app.api.deps.settings.demo_mode", False)
    resp = client.post(URL, json={"amountPaise": 49_900, "customerEmail": "payer@example.com"})
    assert resp.status_code == 404


# --- reconcile ---------------------------------------------------------


def _create(client) -> str:
    resp = client.post(URL, json={"amountPaise": 49_900, "customerEmail": "payer@example.com"})
    assert resp.status_code == 200, resp.text
    return resp.json()["caseId"]


def test_reconcile_paid_link_recovers_the_case_via_the_webhook_path(
    client, db_session, razorpay_stub, monkeypatch
):
    case_id = _create(client)
    monkeypatch.setattr(
        "app.services.test_payment.fetch_payment_link", lambda _id: _paid_link(case_id)
    )

    resp = client.post(
        f"{URL}/reconcile",
        json={
            "paymentLinkId": "plink_TEST1",
            "paymentId": "pay_REAL1",
            "referenceId": case_id,
            "paymentLinkStatus": "paid",
            "signature": _signature("plink_TEST1", case_id, "paid", "pay_REAL1"),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {
        "caseId": case_id,
        "status": "paid",
        "recovered": True,
        "amountPaise": 49_900,
        "paymentId": "pay_REAL1",
        "paymentUrl": "https://rzp.io/i/testlink",
        "signatureValid": True,
    }

    case = db_session.get(Case, case_id)
    assert case.status == "recovered"
    outcome = db_session.get(Outcome, case_id)
    assert outcome.recovered_amount_paise == 49_900
    assert outcome.via == "payment_link"  # derived from the executed Action row
    assert outcome.arm_at_recovery == "treatment"

    events = _events(db_session, case_id)
    assert events[-2:] == [EventType.PAYMENT_VERIFIED, EventType.RECOVERED]


def test_reconcile_is_idempotent_on_refresh(client, db_session, razorpay_stub, monkeypatch):
    case_id = _create(client)
    monkeypatch.setattr(
        "app.services.test_payment.fetch_payment_link", lambda _id: _paid_link(case_id)
    )
    body = {"paymentLinkId": "plink_TEST1", "referenceId": case_id}

    first = client.post(f"{URL}/reconcile", json=body).json()
    second = client.post(f"{URL}/reconcile", json=body).json()

    assert first["recovered"] is True and second["recovered"] is True
    assert first["signatureValid"] is None  # no signature supplied, none checked
    events = _events(db_session, case_id)
    assert events.count(EventType.PAYMENT_VERIFIED) == 1
    assert events.count(EventType.RECOVERED) == 1


def test_reconcile_unpaid_link_leaves_the_case_open(client, db_session, razorpay_stub, monkeypatch):
    case_id = _create(client)
    unpaid = {**_paid_link(case_id), "status": "created", "amount_paid": 0, "payments": []}
    monkeypatch.setattr("app.services.test_payment.fetch_payment_link", lambda _id: unpaid)

    resp = client.post(f"{URL}/reconcile", json={"paymentLinkId": "plink_TEST1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["recovered"] is False
    assert body["status"] == "created"
    assert body["paymentUrl"] == "https://rzp.io/i/testlink"  # so the page can offer "pay now"
    assert db_session.get(Case, case_id).status == "awaiting_customer"
    assert db_session.get(Outcome, case_id) is None
    assert EventType.PAYMENT_VERIFIED not in _events(db_session, case_id)


def test_reconcile_rejects_a_forged_signature_before_touching_razorpay(
    client, db_session, razorpay_stub, monkeypatch
):
    case_id = _create(client)
    monkeypatch.setattr(
        "app.services.test_payment.fetch_payment_link",
        lambda _id: pytest.fail("must not fetch the link when the signature is bad"),
    )

    resp = client.post(
        f"{URL}/reconcile",
        json={
            "paymentLinkId": "plink_TEST1",
            "paymentId": "pay_REAL1",
            "referenceId": case_id,
            "paymentLinkStatus": "paid",
            "signature": "deadbeef" * 8,
        },
    )
    assert resp.status_code == 400
    assert db_session.get(Outcome, case_id) is None


def test_reconcile_does_not_trust_the_redirects_own_status(
    client, db_session, razorpay_stub, monkeypatch
):
    """A correctly signed redirect that says `paid` is still checked against
    Razorpay — the fetch, not the query string, decides."""
    case_id = _create(client)
    unpaid = {**_paid_link(case_id), "status": "created", "amount_paid": 0, "payments": []}
    monkeypatch.setattr("app.services.test_payment.fetch_payment_link", lambda _id: unpaid)

    resp = client.post(
        f"{URL}/reconcile",
        json={
            "paymentLinkId": "plink_TEST1",
            "paymentId": "pay_REAL1",
            "referenceId": case_id,
            "paymentLinkStatus": "paid",
            "signature": _signature("plink_TEST1", case_id, "paid", "pay_REAL1"),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["recovered"] is False
    assert db_session.get(Outcome, case_id) is None


def test_reconcile_after_the_webhook_already_landed_is_a_noop(
    client, db_session, razorpay_stub, monkeypatch
):
    """Both paths can fire; whichever is second must not write a second
    outcome or a PAYMENT_VERIFIED for a recovery the webhook already recorded."""
    from app.services.case_manager import handle_payment_succeeded

    case_id = _create(client)
    handle_payment_succeeded(
        db_session,
        {
            "event": "payment_link.paid",
            "payload": {
                "payment": {
                    "entity": {"id": "pay_WEBHOOK", "order_id": "order_X", "amount": 49_900}
                },
                "payment_link": {"entity": {"id": "plink_TEST1", "reference_id": case_id}},
            },
        },
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.services.test_payment.fetch_payment_link", lambda _id: _paid_link(case_id)
    )

    resp = client.post(f"{URL}/reconcile", json={"paymentLinkId": "plink_TEST1"})
    assert resp.status_code == 200
    assert resp.json()["recovered"] is True
    events = _events(db_session, case_id)
    assert events.count(EventType.RECOVERED) == 1
    assert EventType.PAYMENT_VERIFIED not in events


def test_reconcile_unknown_link_is_404(client, db_session, razorpay_stub, monkeypatch):
    monkeypatch.setattr(
        "app.services.test_payment.fetch_payment_link",
        lambda _id: {"id": _id, "status": "created", "reference_id": None},
    )
    resp = client.post(f"{URL}/reconcile", json={"paymentLinkId": "plink_NOPE"})
    assert resp.status_code == 404


def test_reconcile_maps_razorpays_unknown_id_error_to_404(
    client, db_session, razorpay_stub, monkeypatch
):
    """Razorpay's own answer for a never-issued id is a 400 BadRequestError
    ("id does not exist"); that is a 404 to our caller, not a 502 outage."""
    from razorpay.errors import BadRequestError

    def _raise(_id):
        raise BadRequestError("The id provided does not exist")

    monkeypatch.setattr("app.services.test_payment.fetch_payment_link", _raise)
    resp = client.post(f"{URL}/reconcile", json={"paymentLinkId": "plink_NOPE"})
    assert resp.status_code == 404
    assert "does not exist" in resp.json()["detail"]


# --- signature helper --------------------------------------------------


def test_callback_signature_helper_matches_razorpays_documented_message():
    sig = _signature("plink_1", "case_1", "paid", "pay_1")
    assert verify_payment_link_callback_signature(
        payment_link_id="plink_1",
        reference_id="case_1",
        link_status="paid",
        payment_id="pay_1",
        signature=sig,
        secret=KEY_SECRET,
    )
    # Fails closed on a missing secret and on any tampered field.
    assert not verify_payment_link_callback_signature(
        payment_link_id="plink_1",
        reference_id="case_1",
        link_status="paid",
        payment_id="pay_1",
        signature=sig,
        secret="",
    )
    assert not verify_payment_link_callback_signature(
        payment_link_id="plink_1",
        reference_id="case_1",
        link_status="paid",
        payment_id="pay_2",
        signature=sig,
        secret=KEY_SECRET,
    )
