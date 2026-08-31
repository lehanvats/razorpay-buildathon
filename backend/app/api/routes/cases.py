"""Case list and detail.

    GET /api/cases                   filterable by arm, status, failure_class
    GET /api/cases/{case_id}         case + full append-only timeline

The detail endpoint is the explainability view judges read: webhook received
-> classified SOFT_FUNDS -> LLM proposed retry Sep 2 10:00 (reasoning
verbatim) -> policy approved via salary window -> notice sent -> retry
executed -> recovered Rs 1,499.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/cases", tags=["cases"])


# @router.get("", response_model=list[CaseSummary])
# def list_cases(arm=None, status=None, failure_class=None, db=Depends(get_db)):
#     raise NotImplementedError("step-08: case list")


# @router.get("/{case_id}", response_model=CaseDetail)
# def get_case(case_id: str, db=Depends(get_db)):
#     """Case plus timeline. Timeline is ordered by ts ascending and is never
#     filtered — a redacted audit trail is not an audit trail."""
#     raise NotImplementedError("step-07: case detail + timeline")
