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

from fastapi import APIRouter

router = APIRouter(prefix="/api/demo", tags=["demo"])


# @router.post("/seed")
# def seed(req: SeedRequest, db=Depends(get_db)):
#     """Generate mixed-class failures through Razorpay test mode.
#
#     Must include at least one HARD_DECLINE case run with the loose prompt,
#     so the gate is seen blocking a retry with rule_id HARD_DECLINE_BLOCK.
#     That is the 3:00 beat of the demo video."""
#     raise NotImplementedError("step-08: batch seeder")


# @router.post("/simulate")
# def simulate(db=Depends(get_db)):
#     raise NotImplementedError("step-08: customer simulator")


# @router.post("/reset")
# def reset(db=Depends(get_db)):
#     raise NotImplementedError("step-08: demo reset")
