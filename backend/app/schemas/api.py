"""Request/response models for the REST surface the React app consumes.

Kept separate from the ORM models so the API shape can stay stable while the
schema moves, and separate from proposal.py so the LLM contract is never
accidentally widened by a UI need.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.audit import Actor, EventType
from app.core.holdout import Arm
from app.core.taxonomy import FailureClass
from app.schemas.proposal import Decision


class CaseSummary(BaseModel):
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


class TimelineEntry(BaseModel):
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


class FunnelCounts(BaseModel):
    """failed -> eligible -> treated -> recovered."""

    failed: int
    eligible: int
    treated: int
    recovered: int


class ArmMetrics(BaseModel):
    """Per-arm outcome counts. The control arm is the whole point."""

    arm: Arm
    cases: int
    recovered_cases: int
    recovered_amount_paise: int
    recovery_rate: float


class DashboardMetrics(BaseModel):
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


class EscalationItem(BaseModel):
    """A case awaiting human review, with the reason it stopped."""

    case: CaseSummary
    reason: str
    rule_id: str
    blocked_decision: Decision
    escalated_at: datetime


class SeedRequest(BaseModel):
    """Kick off the demo batch."""

    count: int = Field(default=100, ge=1, le=500)
    seed: int | None = Field(
        default=None,
        description="Fix the RNG so a demo run is reproducible on stage.",
    )
