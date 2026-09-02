"""Human review queue.

    GET  /api/escalations              open escalations, newest first
    POST /api/escalations/{id}/resolve human records a decision

Every item names the rule_id that stopped the agent. "Compliant escalation"
is one of the judged criteria, and an escalation without a stated cause is
just a stuck case.

Resolving is a human action and is audited as Actor.HUMAN — the trail must
distinguish what the agent did from what a person did.

"Open" is derived from the audit trail, not a status column: a case is
`status == "escalated"` and still open only if no ESCALATION_RESOLVED event
has been written for it yet. That is what makes GET /api/escalations need
step-07 to exist, not just step-05's escalated_at/escalation_rule_id columns
— see corrections.md #8 and #14.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import Actor, EventType
from app.core.audit import record as audit_record
from app.db.models import AuditEvent, Case
from app.db.session import get_db
from app.schemas.api import EscalationItem, EscalationResolution
from app.schemas.proposal import Decision
from app.services.case_manager import build_case_summary

router = APIRouter(prefix="/api/escalations", tags=["escalations"])


def _unresolved_escalations_query():
    resolved = (
        select(AuditEvent.id)
        .where(
            AuditEvent.case_id == Case.id,
            AuditEvent.event_type == EventType.ESCALATION_RESOLVED.value,
        )
        .exists()
    )
    return (
        select(Case).where(Case.status == "escalated", ~resolved).order_by(Case.escalated_at.desc())
    )


def _to_item(session: Session, case: Case) -> EscalationItem:
    return EscalationItem(
        case=build_case_summary(session, case),
        reason=case.escalation_reason or "",
        rule_id=case.escalation_rule_id or "",
        # escalate() is only ever called along an ESCALATE-shaped path
        # (verdict.decision == ESCALATE, the LLM's own ESCALATE proposal, a
        # failed diagnosis, or a scheduling failure) — never from a BLOCK
        # verdict, so this is always accurate, not a guess.
        blocked_decision=Decision.ESCALATE,
        escalated_at=case.escalated_at,
    )


@router.get("", response_model=list[EscalationItem])
def list_escalations(db: Session = Depends(get_db)) -> list[EscalationItem]:
    cases = db.execute(_unresolved_escalations_query()).scalars()
    return [_to_item(db, case) for case in cases]


@router.post("/{case_id}/resolve")
def resolve(
    case_id: str, body: EscalationResolution, db: Session = Depends(get_db)
) -> dict[str, str]:
    """Record the human decision. Does NOT resume the agent — a case that
    hit a stopping rule stays stopped."""
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")

    audit_record(
        db,
        case_id=case_id,
        actor=Actor.HUMAN,
        event_type=EventType.ESCALATION_RESOLVED,
        payload={"note": body.note},
    )
    db.commit()
    return {"status": "resolved", "caseId": case_id}
