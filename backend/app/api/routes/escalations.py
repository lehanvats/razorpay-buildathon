"""Human review queue.

    GET  /api/escalations              open escalations, newest first
    POST /api/escalations/{id}/resolve human records a decision

Every item names the rule_id that stopped the agent. "Compliant escalation"
is one of the judged criteria, and an escalation without a stated cause is
just a stuck case.

Resolving is a human action and is audited as Actor.HUMAN — the trail must
distinguish what the agent did from what a person did.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/escalations", tags=["escalations"])


# @router.get("", response_model=list[EscalationItem])
# def list_escalations(db=Depends(get_db)):
#     raise NotImplementedError("step-05: escalation queue")


# @router.post("/{case_id}/resolve")
# def resolve(case_id: str, note: str, db=Depends(get_db)):
#     """Record the human decision. Does NOT resume the agent — a case that
#     hit a stopping rule stays stopped."""
#     raise NotImplementedError("step-05: escalation resolution")
