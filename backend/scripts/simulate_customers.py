"""Play the customer side: pay some links, ignore others.

    python -m scripts.simulate_customers --seed 42

Per-class payment probabilities drive the whole demo, so they must be stated
explicitly in the README — see `app.services.simulation.
PAYMENT_PROBABILITIES` for the exact numbers this run uses. Two properties
the simulation must have or the headline number is meaningless:

  1. **Control cases self-recover too.** Roughly 21% of failed payments
     recover with no outreach at all. If the simulator only pays treated
     cases, the control rate is zero by construction and the incremental
     number is fabricated rather than measured.

  2. **Treatment effect comes from timing, not from a thumb on the scale.**
     A SOFT_FUNDS case should be more likely to pay when retried inside the
     salary window than outside it. That is the mechanism being claimed, so
     it is the mechanism the simulation should model — not a flat bonus
     applied because a case was treated.

Suggested starting probabilities (tune, then document the final numbers):

    class            baseline (control)   treated-in-window   treated-off-window
    SOFT_FUNDS       0.15                 0.55                0.20
    SOFT_TECHNICAL   0.25                 0.50                0.35
    DROPOFF          0.20                 0.45                -
    HARD_DECLINE     0.02                 0.02                -   (never treated)

Runs directly against DATABASE_URL rather than over HTTP: deciding who pays
needs to read case/action state (arm, class, scheduled_for) that there is no
list-and-filter-by-internal-fields API for, and firing the resulting
`payment.captured` still goes through the exact same `handle_payment_succeeded`
path a real webhook would use — see `app.services.simulation`.
"""

import argparse

from app.db.session import SessionLocal
from app.services.simulation import simulate_customers


def main() -> None:
    """Walk open cases and decide, per the probabilities above, whether the
    customer pays — firing the corresponding webhook path if so."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    session = SessionLocal()
    try:
        result = simulate_customers(session, seed=args.seed)
    finally:
        session.close()

    print(f"considered {result['considered']} open cases; {result['paid']} paid")


if __name__ == "__main__":
    main()
