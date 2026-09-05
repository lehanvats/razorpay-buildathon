"""Request/response models for the REST surface the React app consumes.

Kept separate from the ORM models so the API shape can stay stable while the
schema moves, and separate from proposal.py so the LLM contract is never
accidentally widened by a UI need.

Every model here aliases to camelCase on the wire (`order_id` ->
`orderId`) via `CamelModel`, matching `frontend/src/api/types.ts`'s naming —
`populate_by_name=True` means the rest of the backend keeps constructing
these with plain snake_case kwargs (`CaseSummary(order_id=...)`), only JSON
serialization changes.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.core.audit import Actor, EventType
from app.core.holdout import Arm
from app.core.taxonomy import FailureClass
from app.schemas.proposal import Decision


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CaseSummary(CamelModel):
    """One row in the cases table view."""

    id: str
    order_id: str
    amount_paise: int
    method: str
    failure_class: FailureClass
    arm: Arm
    status: str
    attempts_used: int
    created_at: datetime
    recovered_amount_paise: int | None = None


class TimelineEntry(CamelModel):
    """One audit event, rendered as a row on the case detail timeline."""

    ts: datetime
    actor: Actor
    event_type: EventType
    payload: dict
    rule_id: str | None = None


class CaseDetail(CaseSummary):
    """Case plus its full append-only timeline — the explainability view.

    Judges read this screen: webhook received -> classified SOFT_FUNDS ->
    LLM proposed retry (reasoning verbatim) -> policy approved via salary
    window -> notice sent -> retry executed -> recovered Rs 1,499.
    """

    timeline: list[TimelineEntry]


class FunnelCounts(CamelModel):
    """failed -> eligible -> treated -> recovered."""

    failed: int
    eligible: int
    treated: int
    recovered: int


class ArmMetrics(CamelModel):
    """Per-arm outcome counts. The control arm is the whole point."""

    arm: Arm
    cases: int
    recovered_cases: int
    recovered_amount_paise: int
    recovery_rate: float


class DashboardMetrics(CamelModel):
    """The headline screen: gross vs incremental, side by side.

    `gross_recovered_paise` is what every vendor in this market reports.
    `incremental_recovered_paise` is treated minus control — the number
    nobody else publishes, and the reason the holdout exists.
    """

    funnel: FunnelCounts
    gross_recovered_paise: int
    incremental_recovered_paise: int
    treatment: ArmMetrics
    control: ArmMetrics
    by_failure_class: dict[FailureClass, ArmMetrics]
    escalations_open: int


class EscalationItem(CamelModel):
    """A case awaiting human review, with the reason it stopped."""

    case: CaseSummary
    reason: str
    rule_id: str
    blocked_decision: Decision
    escalated_at: datetime


class EscalationResolution(CamelModel):
    """Body of `POST /api/escalations/{id}/resolve`. The note is the only
    thing this endpoint records — see that route's docstring for why it does
    not resume the agent."""

    note: str = Field(min_length=1)


class SeedRequest(CamelModel):
    """Kick off the demo batch."""

    count: int = Field(default=100, ge=1, le=500)
    seed: int | None = Field(
        default=None,
        description="Fix the RNG so a demo run is reproducible on stage.",
    )


class TestPaymentRequest(CamelModel):
    """Body of `POST /api/test-payment` — one simulated abandoned checkout
    the operator will then pay for real on Razorpay's test checkout."""

    amount_paise: int = Field(
        ge=100,
        le=50_000_000,
        description="Rs 1 to Rs 5,00,000, in paise. Razorpay's own minimum is Rs 1.",
    )
    customer_email: str = Field(
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="Stamped on the case and the payment link; Razorpay "
        "notifies this address in test mode too.",
    )


class TestPaymentResult(CamelModel):
    case_id: str
    payment_link_id: str
    payment_url: str
    amount_paise: int
    status: str


class PaymentReconcileRequest(CamelModel):
    """Body of `POST /api/test-payment/reconcile`: the query parameters
    Razorpay appends to the callback redirect, forwarded verbatim by the
    `/pay/return` page. Everything but the link id is optional because a
    payer can land on that page without having paid (or by hand)."""

    payment_link_id: str = Field(min_length=1, max_length=64)
    payment_id: str | None = Field(default=None, max_length=64)
    reference_id: str | None = Field(default=None, max_length=64)
    payment_link_status: str | None = Field(default=None, max_length=32)
    signature: str | None = Field(default=None, max_length=128)


class PaymentReconcileResult(CamelModel):
    case_id: str
    status: str
    """Razorpay's own link status: created | partially_paid | paid | expired | cancelled."""
    recovered: bool
    amount_paise: int
    payment_id: str | None = None
    payment_url: str | None = None
    signature_valid: bool | None = None
    """None when the redirect carried no signature to check."""
