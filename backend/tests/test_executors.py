"""Executor tests: each takes a Verdict, touches the outside world through a
monkeypatched module-level function (never the real Razorpay/Resend network),
and reports success/failure as an ExecutionResult rather than raising.

`create_order` / `create_payment_link` / `send_email` are patched as the
names imported into each executor module (`app.executors.retry.create_order`,
etc.), matching the pattern `app.services.case_manager.diagnose` already
uses — the executor calls the bare name, not `razorpay_client.create_order`.
"""

from datetime import UTC, datetime

import pytest

from app.db.models import Case
from app.executors.dunning import DunningExecutor, PreDebitNoticeExecutor
from app.executors.payment_link import PaymentLinkExecutor
from app.executors.retry import RetryExecutor
from app.schemas.proposal import ActionKind, Channel, Decision, Verdict


def _make_case(db_session, **overrides) -> Case:
    defaults = dict(
        id="case_exec_test",
        razorpay_order_id="order_EXEC",
        razorpay_payment_id="pay_EXEC",
        customer_email="customer@example.com",
        amount_paise=200_000,
        currency="INR",
        method="upi",
        is_mandate=False,
        failure_class="SOFT_TECHNICAL",
        arm="treatment",
        status="scheduled",
        attempts_used=1,
        messages_sent=0,
        discount_offered=False,
    )
    defaults.update(overrides)
    case = Case(**defaults)
    db_session.add(case)
    db_session.flush()
    return case


def _verdict(**overrides) -> Verdict:
    defaults = dict(
        decision=Decision.APPROVE,
        rule_id="PASS",
        effective_action=ActionKind.SCHEDULE_RETRY,
        explanation="test verdict",
    )
    defaults.update(overrides)
    return Verdict(**defaults)


# --- RetryExecutor -----------------------------------------------------


def test_retry_executor_creates_order_and_increments_attempts(db_session, monkeypatch):
    case = _make_case(db_session, attempts_used=1)
    monkeypatch.setattr(
        "app.executors.retry.create_order", lambda *a, **kw: {"id": "order_NEW_RETRY"}
    )

    result = RetryExecutor().execute(db_session, case.id, _verdict())

    assert result.ok is True
    assert result.razorpay_ref == "order_NEW_RETRY"
    assert db_session.get(Case, case.id).attempts_used == 2


def test_retry_executor_reports_failure_without_incrementing_attempts(db_session, monkeypatch):
    case = _make_case(db_session, attempts_used=1)

    def _raise(*a, **kw):
        raise RuntimeError("razorpay 500")

    monkeypatch.setattr("app.executors.retry.create_order", _raise)

    result = RetryExecutor().execute(db_session, case.id, _verdict())

    assert result.ok is False
    assert "razorpay 500" in result.error
    assert db_session.get(Case, case.id).attempts_used == 1


# --- PaymentLinkExecutor -------------------------------------------------


def test_payment_link_executor_creates_link_for_full_amount(db_session, monkeypatch):
    case = _make_case(db_session, amount_paise=200_000)
    captured = {}

    def _create(amount_paise, email, **notes):
        captured["amount_paise"] = amount_paise
        captured["email"] = email
        captured["case_id"] = notes.get("case_id")
        return {"id": "plink_1", "short_url": "https://rzp.io/x"}

    monkeypatch.setattr("app.executors.payment_link.create_payment_link", _create)

    result = PaymentLinkExecutor().execute(
        db_session, case.id, _verdict(effective_action=ActionKind.SEND_PAYMENT_LINK)
    )

    assert result.ok is True
    assert result.razorpay_ref == "plink_1"
    assert captured["amount_paise"] == 200_000
    assert captured["case_id"] == case.id
    assert db_session.get(Case, case.id).discount_offered is False


def test_payment_link_executor_applies_discount_and_marks_offered(db_session, monkeypatch):
    case = _make_case(db_session, amount_paise=200_000, discount_offered=False)
    captured = {}

    def _create(amount_paise, email, **kw):
        captured["amount_paise"] = amount_paise
        return {"id": "plink_2"}

    monkeypatch.setattr("app.executors.payment_link.create_payment_link", _create)

    verdict = _verdict(effective_action=ActionKind.OFFER_DISCOUNT, effective_discount_percent=10)
    result = PaymentLinkExecutor().execute(db_session, case.id, verdict)

    assert result.ok is True
    assert captured["amount_paise"] == 180_000  # 10% off 200,000
    assert db_session.get(Case, case.id).discount_offered is True


def test_payment_link_executor_fails_without_customer_email(db_session):
    case = _make_case(db_session, customer_email=None)

    result = PaymentLinkExecutor().execute(db_session, case.id, _verdict())

    assert result.ok is False
    assert "email" in result.error


# --- DunningExecutor -------------------------------------------------


def test_dunning_executor_sends_draft_and_updates_contact_counters(db_session, monkeypatch):
    case = _make_case(db_session, messages_sent=0)
    monkeypatch.setattr("app.executors.dunning.send_email", lambda *a, **kw: "msg_123")

    verdict = _verdict(
        effective_action=ActionKind.SEND_PAYMENT_LINK,
        message_draft="Please complete your payment.",
        channel=Channel.EMAIL,
    )
    result = DunningExecutor().execute(db_session, case.id, verdict)

    assert result.ok is True
    updated = db_session.get(Case, case.id)
    assert updated.messages_sent == 1
    assert updated.last_contact_at is not None


def test_dunning_executor_refuses_to_invent_a_fallback_message(db_session, monkeypatch):
    """Never substitute a hand-written fallback silently — a missing draft
    fails the action so it is visible, not sent as generic copy."""
    case = _make_case(db_session)
    monkeypatch.setattr(
        "app.executors.dunning.send_email",
        lambda *a, **kw: pytest.fail("send_email must not be called without a draft"),
    )

    result = DunningExecutor().execute(db_session, case.id, _verdict(message_draft=None))

    assert result.ok is False
    assert db_session.get(Case, case.id).messages_sent == 0


def test_dunning_executor_reports_failure_when_send_email_raises(db_session, monkeypatch):
    """Executor.execute's contract (executors/base.py) says 'must not raise' —
    a Resend transport error must come back as ExecutionResult(ok=False),
    not propagate out of execute()."""
    case = _make_case(db_session, messages_sent=0)

    def _raise(*a, **kw):
        raise RuntimeError("resend 500")

    monkeypatch.setattr("app.executors.dunning.send_email", _raise)

    result = DunningExecutor().execute(
        db_session, case.id, _verdict(message_draft="Please complete your payment.")
    )

    assert result.ok is False
    assert "resend 500" in result.error
    updated = db_session.get(Case, case.id)
    assert updated.messages_sent == 0
    assert updated.last_contact_at is None


# --- PreDebitNoticeExecutor -------------------------------------------------


def test_pre_debit_notice_executor_stamps_notice_without_touching_contact_counters(
    db_session, monkeypatch
):
    """Compliance, not persuasion: must never move messages_sent or
    last_contact_at, since those feed the anti-spam cooldown rule."""
    case = _make_case(db_session, is_mandate=True, messages_sent=2)
    monkeypatch.setattr("app.executors.dunning.send_email", lambda *a, **kw: "msg_notice")

    verdict = _verdict(effective_timing=datetime(2026, 9, 5, 9, 0, tzinfo=UTC))
    result = PreDebitNoticeExecutor().execute(db_session, case.id, verdict)

    assert result.ok is True
    updated = db_session.get(Case, case.id)
    assert updated.pre_debit_notice_sent_at is not None
    assert updated.messages_sent == 2  # unchanged
    assert updated.last_contact_at is None  # unchanged


def test_pre_debit_notice_executor_reports_failure_when_send_email_raises(db_session, monkeypatch):
    """Same 'must not raise' contract as DunningExecutor — this one matters
    more: schedule() in scheduler/poller.py treats a failed notice as reason
    to refuse scheduling the debit at all (see SchedulingFailed)."""
    case = _make_case(db_session, is_mandate=True, messages_sent=0)

    def _raise(*a, **kw):
        raise RuntimeError("resend 500")

    monkeypatch.setattr("app.executors.dunning.send_email", _raise)

    verdict = _verdict(effective_timing=datetime(2026, 9, 5, 9, 0, tzinfo=UTC))
    result = PreDebitNoticeExecutor().execute(db_session, case.id, verdict)

    assert result.ok is False
    assert "resend 500" in result.error
    assert db_session.get(Case, case.id).pre_debit_notice_sent_at is None
