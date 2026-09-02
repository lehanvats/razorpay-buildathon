"""Case list and detail.

    GET /api/cases                   filterable by arm, status, failure_class
    GET /api/cases/{case_id}         case + full append-only timeline

The detail endpoint is the explainability view judges read: webhook received
-> classified SOFT_FUNDS -> LLM proposed retry Sep 2 10:00 (reasoning
verbatim) -> policy approved via salary window -> notice sent -> retry
executed -> recovered Rs 1,499.

Only the detail route is implemented here (step-07's scope — the audit
trail). The list route stays commented, `TODO(step-08)`: it needs the
dashboard's filtering conventions decided alongside it, and the frontend has
nowhere to call it from yet either (`api/client.ts`'s fetch wrapper,
`App.tsx`'s routing and `CasesPage.tsx` are all still stubs tagged
step-08) — see corrections.md for the same judgment call made about
CaseTimeline.tsx/CaseDetailPage.tsx.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Case, Outcome
from app.db.session import get_db
from app.schemas.api import CaseDetail
from app.services.case_manager import get_timeline

router = APIRouter(prefix="/api/cases", tags=["cases"])


# @router.get("", response_model=list[CaseSummary])
# def list_cases(arm=None, status=None, failure_class=None, db=Depends(get_db)):
#     raise NotImplementedError("step-08: case list")


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: str, db: Session = Depends(get_db)) -> CaseDetail:
    """Case plus timeline. Timeline is ordered by ts ascending and is never
    filtered — a redacted audit trail is not an audit trail."""
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")

    outcome = db.execute(select(Outcome).where(Outcome.case_id == case_id)).scalar_one_or_none()

    return CaseDetail(
        id=case.id,
        order_id=case.razorpay_order_id,
        amount_paise=case.amount_paise,
        method=case.method,
        failure_class=case.failure_class,
        arm=case.arm,
        status=case.status,
        attempts_used=case.attempts_used,
        created_at=case.created_at,
        recovered_amount_paise=outcome.recovered_amount_paise if outcome else None,
        timeline=get_timeline(db, case_id),
    )
