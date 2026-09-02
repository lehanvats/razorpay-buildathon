"""Case list and detail.

    GET /api/cases                   filterable by arm, status, failure_class
    GET /api/cases/{case_id}         case + full append-only timeline

The detail endpoint is the explainability view judges read: webhook received
-> classified SOFT_FUNDS -> LLM proposed retry Sep 2 10:00 (reasoning
verbatim) -> policy approved via salary window -> notice sent -> retry
executed -> recovered Rs 1,499.

The list route is newest-first with no default filter — the frontend's
CasesPage applies arm/status/failure_class as query params only when the
operator picks one.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.holdout import Arm
from app.core.taxonomy import FailureClass
from app.db.models import Case
from app.db.session import get_db
from app.schemas.api import CaseDetail, CaseSummary
from app.services.case_manager import build_case_summary, get_timeline

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("", response_model=list[CaseSummary])
def list_cases(
    arm: Arm | None = None,
    status: str | None = None,
    failure_class: FailureClass | None = None,
    db: Session = Depends(get_db),
) -> list[CaseSummary]:
    query = select(Case).order_by(Case.created_at.desc())
    if arm is not None:
        query = query.where(Case.arm == arm.value)
    if status is not None:
        query = query.where(Case.status == status)
    if failure_class is not None:
        query = query.where(Case.failure_class == failure_class.value)

    cases = db.execute(query).scalars()
    return [build_case_summary(db, case) for case in cases]


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: str, db: Session = Depends(get_db)) -> CaseDetail:
    """Case plus timeline. Timeline is ordered by ts ascending and is never
    filtered — a redacted audit trail is not an audit trail."""
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")

    summary = build_case_summary(db, case)
    return CaseDetail(**summary.model_dump(), timeline=get_timeline(db, case_id))
