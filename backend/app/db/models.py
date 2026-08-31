"""ORM models — the four tables from the blueprint, plus raw webhook storage.

    cases         id, order_id, amount, method, failure_class, arm, status, attempts_used
    actions       id, case_id, kind, scheduled_for, executed_at, result
    audit_events  id, case_id, actor, type, payload_json, ts   -- append-only
    outcomes      case_id, recovered_amount, recovered_at, via
    webhook_events  raw payloads, stored before any processing

Money is stored in paise as an integer everywhere. Never float, never rupees.
Timestamps are timezone-aware UTC in the column; IST is a presentation
concern (the salary-window rule reasons in IST — see policy/rules.py).

Step-01 implements `webhook_events` only. The other four tables are fenced
off below rather than half-declared: a class inheriting Base with no primary
key raises at import time, and a partially-declared table would produce a
migration that lies about what step-01 delivers.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WebhookEvent(Base):
    """Raw Razorpay webhook payloads, stored before any processing.

    Two jobs: an audit-grade record of exactly what the gateway sent us, and
    idempotency. Razorpay redelivers webhooks, so `event_id` is unique and a
    duplicate delivery is a no-op rather than a second case or a second
    retry.

    Only signature-verified payloads are persisted. An unverified body is
    dropped at the route with 400 and never reaches this table — otherwise
    any unauthenticated caller could write rows at will. `signature_valid`
    is therefore always True today; it exists so that adding a quarantine
    path later is a code change, not a migration.
    """

    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    event_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    """The dedupe key — Razorpay's `X-Razorpay-Event-Id` header. The UNIQUE
    constraint, not a prior SELECT, is what makes redelivery a no-op: a
    read-then-write check races against exactly the concurrent redelivery
    that dedupe exists to absorb."""

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """`payload["event"]` — e.g. payment.failed, payment.captured, order.paid."""

    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)

    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    """The parsed body. Parsed, not raw, because the raw bytes' only job was
    the signature check, which has already passed by the time we store."""

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """NULL until the case manager has handled it. A crash between insert and
    dispatch leaves a replayable row rather than a lost event."""

    def __repr__(self) -> str:
        return f"<WebhookEvent {self.event_type} {self.event_id}>"


# --------------------------------------------------------------------------
# TODO(step-02/03/06/07): the case tables.
#
# Deliberately commented out rather than declared empty. Uncomment each class
# in its step and add columns; the shape below is the agreed schema.
#
# class Case(Base):
#     """The unit everything else operates on.
#
#     Opened by a `payment.failed` event. `failure_class` and `arm` are written
#     once at creation and never recomputed — a case is audited under the class
#     and arm it was actually acted on.
#
#     Columns:
#         id (uuid), razorpay_order_id, razorpay_payment_id, customer_email,
#         amount_paise, currency, method, is_mandate,
#         failure_class, failure_reason_raw,
#         arm, status, attempts_used, messages_sent,
#         last_contact_at, pre_debit_notice_sent_at, discount_offered,
#         created_at, closed_at
#
#     `status`: open | scheduled | awaiting_customer | recovered | escalated |
#     exhausted | control_observed.
#     """
#
#     __tablename__ = "cases"
#     # TODO(step-02): columns + indexes on (arm), (status), (failure_class)
#
#
# class Action(Base):
#     """One approved, scheduled or executed intervention.
#
#     A row is written only after the policy gate approves — there is no path
#     from a Proposal to this table. `scheduled_for` is what the poller claims
#     on (see scheduler/), which is why durable delay needs no external service.
#
#     Columns:
#         id, case_id, kind, verdict_rule_id, scheduled_for, executed_at,
#         result, error, razorpay_ref (order/payment-link id), payload_json
#     """
#
#     __tablename__ = "actions"
#     # TODO(step-06): columns + index on (scheduled_for, executed_at) for the poller
#
#
# class AuditEvent(Base):
#     """Append-only. Written exclusively by core/audit.py.
#
#     No ORM update or delete path is defined for this model on purpose. If you
#     find yourself needing one, the answer is a new event, not an edit.
#
#     Columns:
#         id, case_id, actor, event_type, payload_json, ts
#     """
#
#     __tablename__ = "audit_events"
#     # TODO(step-07): columns + index on (case_id, ts) for timeline rendering
#
#
# class Outcome(Base):
#     """Terminal result of a case — how the money came back, if it did.
#
#     Written for control cases too. A control case that self-recovers MUST
#     land here, otherwise the control recovery rate reads as zero and the
#     incremental metric flatters us. See services/case_manager.py.
#
#     Columns:
#         case_id (pk), recovered_amount_paise, recovered_at,
#         via (retry | payment_link | self | none), arm_at_recovery
#     """
#
#     __tablename__ = "outcomes"
#     # TODO(step-03): columns
# --------------------------------------------------------------------------
