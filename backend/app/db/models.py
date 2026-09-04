"""ORM models — the four tables from the blueprint, plus raw webhook storage.

    cases         id, order_id, amount, method, failure_class, arm, status, attempts_used
    actions       id, case_id, kind, scheduled_for, executed_at, result
    audit_events  id, case_id, actor, type, payload_json, ts   -- append-only
    outcomes      case_id, recovered_amount, recovered_at, via
    webhook_events  raw payloads, stored before any processing

Money is stored in paise as an integer everywhere. Never float, never rupees.
Timestamps are timezone-aware UTC in the column; IST is a presentation
concern (the salary-window rule reasons in IST — see policy/rules.py).

Step-01 implemented `webhook_events`; step-02 added `cases`; step-03 added
`outcomes`; step-05 added the `cases.escalated_at`/`escalation_rule_id`/
`escalation_reason` columns; step-06 added `actions` and `cases.last_diagnosed_at`;
step-07 added `audit_events`; step-08 added `cases.demo_loose_prompt`.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Case(Base):
    """The unit everything else operates on.

    Opened by a `payment.failed` event. `failure_class` and `arm` are written
    once at creation and never recomputed — a case is audited under the class
    and arm it was actually acted on.

    `failure_class` and `arm` are stored as plain strings, not a native
    Postgres enum: adding a class later is then a code change, not a
    migration. Money is paise, integer, never float (see module docstring).

    `status`: open | scheduled | awaiting_customer | recovered | escalated |
    exhausted | control_observed.
    """

    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    razorpay_order_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    """One case per order. Razorpay allows several payment attempts against
    one Order before it settles, so a repeat `payment.failed` for an order
    that already has a case must not open a second one — the UNIQUE
    constraint is the backstop for that, not just the read-check-write in
    services/case_manager.py."""

    razorpay_payment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    """The payment attempt that opened the case. Later retries get their own
    `actions.razorpay_ref`, not a new case."""

    customer_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    is_mandate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    """True for subscription / e-mandate / UPI AutoPay debits. Gates the RBI
    24-hour pre-debit notification rule."""

    failure_class: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    failure_reason_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    """Razorpay's `error_reason` verbatim — kept alongside the derived class
    so a taxonomy change can be audited against what was actually observed."""

    arm: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open", index=True)
    attempts_used: Mapped[int] = mapped_column(nullable=False, default=1)
    """Charge attempts spent so far, original included. NPCI caps AutoPay at
    1 original + 3 retries — see policy/rules.py:MAX_CHARGE_ATTEMPTS."""

    messages_sent: Mapped[int] = mapped_column(nullable=False, default=0)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pre_debit_notice_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    discount_offered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalation_rule_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """The policy.rules.RuleId that stopped the agent — e.g.
    LOW_CONFIDENCE_ESCALATE, ATTEMPT_BUDGET_EXHAUSTED. Denormalised onto the
    case (rather than requiring a join to audit_events) so the step-08
    escalation queue can list open escalations before step-07 exists."""
    escalation_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    """Verdict.explanation verbatim, for the human reviewer."""

    last_diagnosed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """NULL until the first `advance_case` pass. This, not `status`, is what
    `scheduler.poller.claim_new_cases` gates on: a proposal the gate BLOCKs
    (e.g. CONTACT_COOLDOWN) leaves `status == "open"` with no `actions` row,
    which is otherwise indistinguishable from a case that was never
    diagnosed at all — without this column the poller would re-diagnose (and
    re-spend an LLM call on) a blocked case every single poll tick."""

    demo_loose_prompt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    """Demo-only. `services.seeding.seed_batch` sets this True on exactly one
    seeded HARD_DECLINE case so `advance_case` diagnoses it with
    `agent.prompts.DEMO_LOOSE_SYSTEM_PROMPT` instead of the real system
    prompt — the model then proposes a retry on an unrecoverable case and
    `policy.rules.hard_decline_block` is seen refusing it, on screen, with
    its rule_id. That is the 3:00 beat of the demo video (BUILD-PLAN.md).
    Never true outside a seeded demo case."""

    def __repr__(self) -> str:
        return f"<Case {self.id} {self.failure_class}/{self.arm}>"


class Outcome(Base):
    """Terminal result of a case — how the money came back, if it did.

    Written for control cases too. A control case that self-recovers MUST
    land here, otherwise the control recovery rate reads as zero and the
    incremental metric flatters us. See services/case_manager.handle_payment_succeeded.

    One row per case (`case_id` is the primary key): a case reaches a
    terminal recovered state at most once, so there is nothing to append.
    """

    __tablename__ = "outcomes"

    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id"), primary_key=True)

    recovered_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    via: Mapped[str] = mapped_column(String(16), nullable=False)
    """retry | payment_link | self | none. Until step-06 adds the `actions`
    table there is nothing to correlate a recovery against, so every recovery
    is currently written as "self" — see TODO(step-06) in case_manager.py."""

    arm_at_recovery: Mapped[str] = mapped_column(String(16), nullable=False)
    """Snapshot of `cases.arm` at recovery time. Denormalised on purpose: the
    metrics query (services/metrics.py) group-bys this table alone and should
    not need a join back to `cases` to compute the control/treatment split."""

    def __repr__(self) -> str:
        return f"<Outcome {self.case_id} {self.recovered_amount_paise}p via {self.via}>"


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
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """NULL until the case manager has handled it. A crash between insert and
    dispatch leaves a replayable row rather than a lost event."""

    def __repr__(self) -> str:
        return f"<WebhookEvent {self.event_type} {self.event_id}>"


class Action(Base):
    """One approved, scheduled or executed intervention.

    A row is written only after the policy gate approves — there is no path
    from a Proposal to this table (`services/case_manager.advance_case`
    calls `scheduler.poller.schedule`, never constructs this directly).
    `scheduled_for` is what the poller claims on, which is why durable delay
    needs no external service.

    Claim/execution lifecycle, all nullable-until-set:
        claimed_at    stamped by claim_due_actions under `FOR UPDATE SKIP
                      LOCKED`; the second half of the poller's claim gate
                      alongside `executed_at IS NULL`.
        executed_at   stamped by dispatch() immediately before the first
                      executor touches the network — "claim the action row
                      before touching the network" from executors/base.py.
                      A transport failure with retries left CLEARS both
                      columns so the row is reclaimable; a permanent
                      failure (dispatch_attempts exhausted, or the case
                      moved on) leaves both set with result=False.
        dispatch_attempts  transport-failure counter (Razorpay/Resend 5xx,
                      timeouts), distinct from the NPCI charge-attempt
                      budget on `cases.attempts_used` — a dispatch that
                      never reached Razorpay must not consume a regulatory
                      retry.
        result        True/False once executed_at is set; None while
                      pending.
        razorpay_ref  the order or payment-link id an executor created, for
                      later correlation (see PaymentLinkExecutor's
                      `reference_id` and the payment_link.paid fallback
                      lookup in case_manager.py).
        payload_json  the full `Verdict` this action was scheduled from
                      (`verdict.model_dump(mode="json")`), so dispatch() can
                      reconstruct it without a second gate() call — the
                      Executor protocol only knows Verdict, not Action.
        completed_executors  class names (e.g. "PaymentLinkExecutor") of
                      fan-out steps that already succeeded on a prior
                      dispatch attempt for this row. A transport failure
                      partway through a multi-executor fan-out (e.g.
                      SEND_PAYMENT_LINK's link-then-email pair) releases the
                      claim for retry — without this, the retry re-ran every
                      executor from the top, including ones that had already
                      created a real, non-idempotent side effect (a second
                      live payment link). dispatch() consults this list to
                      skip steps already done, rather than re-running them.
    """

    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    """An `ActionKind` value — `verdict.effective_action` at scheduling time."""

    verdict_rule_id: Mapped[str] = mapped_column(String(64), nullable=False)

    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatch_attempts: Mapped[int] = mapped_column(nullable=False, default=0)

    result: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    razorpay_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    completed_executors: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_actions_poller_claim", "scheduled_for", "executed_at", "claimed_at"),
    )

    def __repr__(self) -> str:
        return f"<Action {self.id} {self.kind} case={self.case_id}>"


class AuditEvent(Base):
    """Append-only. Written exclusively by core/audit.py — no ORM update or
    delete path is defined for this model on purpose. If you find yourself
    needing one, the answer is a new event, not an edit.

    `ts` uses `server_default=func.now()`, which is the Postgres *transaction*
    timestamp, not the wall clock — several events written in one request
    (e.g. CASE_OPENED/ARM_ASSIGNED/CLASSIFIED in handle_payment_failed) land
    with byte-identical `ts`. `id`'s insertion-ordered sequence is therefore
    the real tiebreaker; `services/case_manager.get_timeline` orders by
    `(ts, id)`, never `ts` alone.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id"), nullable=False)
    """Not separately indexed: `ix_audit_events_case_id_ts` below covers a
    case_id-only lookup as its leftmost prefix, so a second single-column
    index would just be write overhead on an append-only table."""
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    """A `core.audit.Actor` value."""
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    """A `core.audit.EventType` value."""
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    """Never null: `core.audit.record` stores `{}` rather than omitting the
    column, so `TimelineEntry.payload` (a required field, no default) never
    has to handle a missing value at the API boundary."""

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_audit_events_case_id_ts", "case_id", "ts"),)

    def __repr__(self) -> str:
        return f"<AuditEvent {self.id} {self.event_type} case={self.case_id}>"
