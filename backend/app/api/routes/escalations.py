"""Human review queue.

    GET  /api/escalations              open escalations, newest first
    POST /api/escalations/{id}/resolve human records a decision

Every item names the rule_id that stopped the agent. "Compliant escalation"
is one of the judged criteria, and an escalation without a stated cause is
just a stuck case.

Resolving is a human action and is audited as Actor.HUMAN — the trail must
distinguish what the agent did from what a person did.

Deferred to step-08 (dashboard), not step-05: `services/case_manager.escalate()`
now writes `cases.escalated_at`/`escalation_rule_id`/`escalation_reason`, which
is enough to implement GET below today. But POST /resolve's `note` has no
durable home until step-07's audit trail exists — recording it anywhere else
would be a throwaway mechanism step-07 immediately replaces. Building the read
route without the write route the same screen needs isn't worth doing twice;
see corrections.md.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/escalations", tags=["escalations"])


# @router.get("", response_model=list[EscalationItem])
# def list_escalations(db=Depends(get_db)):
#     raise NotImplementedError("step-08: escalation queue")


# @router.post("/{case_id}/resolve")
# def resolve(case_id: str, note: str, db=Depends(get_db)):
#     """Record the human decision. Does NOT resume the agent — a case that
#     hit a stopping rule stays stopped."""
#     raise NotImplementedError("step-08: escalation resolution")
