"""Demo controls — seeding and customer simulation.

    POST /api/demo/seed       fire ~100 mixed-class failed payments
    POST /api/demo/simulate   play the customers paying (or not)
    POST /api/demo/reset      clear all cases and start over

Gated behind `settings.demo_mode`; returns 404 when disabled so it cannot be
reached from anything pointed at live keys.

Be explicit in the README that customer behaviour is simulated, and state the
assumed per-class payment probabilities. A judged demo that names its
simulation beats one that hides it.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_demo_mode
from app.db.models import Action, AuditEvent, Case, Outcome, WebhookEvent
from app.schemas.api import SeedRequest
from app.services.seeding import seed_batch
from app.services.simulation import simulate_customers

router = APIRouter(prefix="/api/demo", tags=["demo"], dependencies=[Depends(require_demo_mode)])


@router.post("/seed")
def seed(req: SeedRequest, db: Session = Depends(get_db)) -> dict:
    """Generate mixed-class failures in-process (see services.seeding for
    why this doesn't go over HTTP the way scripts/seed_failures.py does).

    Always includes at least one HARD_DECLINE case run with the loose
    prompt, so the gate is seen blocking a retry with rule_id
    HARD_DECLINE_BLOCK. That is the 3:00 beat of the demo video."""
    return seed_batch(db, count=req.count, seed=req.seed)


@router.post("/simulate")
def simulate(db: Session = Depends(get_db)) -> dict:
    return simulate_customers(db)


@router.post("/reset")
def reset(db: Session = Depends(get_db)) -> dict:
    """Clear every case-related table so a demo can be re-run from zero.

    Deletion order respects the FK graph (events/outcomes/actions before the
    cases they reference); `webhook_events` has no FK to anything else so it
    can go last."""
    for model in (AuditEvent, Outcome, Action, Case, WebhookEvent):
        db.execute(delete(model))
    db.commit()
    return {"status": "reset"}
