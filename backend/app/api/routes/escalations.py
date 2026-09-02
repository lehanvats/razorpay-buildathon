"""Human review queue.

    GET  /api/escalations              open escalations, newest first
    POST /api/escalations/{id}/resolve human records a decision

Every item names the rule_id that stopped the agent. "Compliant escalation"
is one of the judged criteria, and an escalation without a stated cause is
just a stuck case.

Resolving is a human action and is audited as Actor.HUMAN — the trail must
distinguish what the agent did from what a person did.

Deferred to step-08 (dashboard), not step-05 or step-07: `services/
case_manager.escalate()` writes `cases.escalated_at`/`escalation_rule_id`/
`escalation_reason`, and `core/audit.py` (step-07) now gives POST /resolve's
`note` a durable home — a new `core.audit.EventType` member and an
`audit.record(..., actor=Actor.HUMAN, ...)` call, both trivial additions.
Both routes are implementable today. Left commented anyway: building the
read route without the write route the same screen needs isn't worth doing
twice, and step-08 is where the dashboard's filtering/list conventions get
decided — this screen shares them. See corrections.md.
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
