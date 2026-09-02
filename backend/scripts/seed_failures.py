"""Seed the demo batch: ~100 mixed-class failed payments through test mode.

    python -m scripts.seed_failures --count 100 --seed 42

Class mix should roughly reflect the Indian market rather than being uniform
— insufficient funds dominates mandate failures, technical declines cluster
on specific banks. State the chosen mix in the README; a demo that names its
assumptions beats one that hides them. See `app.services.seeding.
FAILURE_CLASS_MIX` for the exact weights.

Must include at least one HARD_DECLINE case flagged to run with the loose
prompt, so the gate is observed blocking a retry on screen. That is the
3:00 beat of the video.

Posts real, signed HTTP requests at a *running* server's `/api/webhooks/
razorpay` — the same route Razorpay itself would call — rather than seeding
in-process, specifically to prove the real signature-verified ingress path
on camera. `api.routes.demo`'s `POST /seed` is the in-process cousin, used by
the frontend's "seed" button; see that module for why the two differ.

The demo_loose_prompt flag can only be set once the case row exists (its id
is server-assigned), so this connects to DATABASE_URL directly afterwards
and flips it on the one HARD_DECLINE case's row by order_id — the same
"talk to the DB the app is actually using" idiom as scripts/dbq.py.
"""

import argparse
import json
import random
import sys
from collections import Counter

import httpx
from sqlalchemy import create_engine, text

from app.config import settings
from app.core.taxonomy import FailureClass
from app.integrations.razorpay_client import sign_payload
from app.services.seeding import build_failure_event, pick_class


def _post_one(client: httpx.Client, base_url: str, event: dict) -> httpx.Response:
    body = json.dumps(event).encode()
    signature = sign_payload(body, settings.razorpay_webhook_secret)
    return client.post(
        f"{base_url}/api/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"},
    )


def main() -> None:
    """Generate failures, POST them at the webhook route with valid
    signatures, and report the resulting class/arm split so the operator can
    see the holdout is roughly 20% before the demo starts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    if not settings.razorpay_webhook_secret:
        print("RAZORPAY_WEBHOOK_SECRET is not set; cannot sign webhooks.", file=sys.stderr)
        sys.exit(1)

    rng = random.Random(args.seed)
    classes = [pick_class(rng) for _ in range(args.count)]
    if FailureClass.HARD_DECLINE not in classes:
        classes[0] = FailureClass.HARD_DECLINE
    demo_order_id: str | None = None

    by_class: Counter[str] = Counter()
    failures = 0

    with httpx.Client(timeout=10.0) as client:
        for failure_class in classes:
            event = build_failure_event(rng, failure_class=failure_class)
            order_id = event["payload"]["payment"]["entity"]["order_id"]
            resp = _post_one(client, args.base_url, event)
            if resp.status_code != 200 or resp.json().get("status") not in (
                "accepted",
                "duplicate",
            ):
                failures += 1
                print(f"  FAIL {order_id}: {resp.status_code} {resp.text}", file=sys.stderr)
                continue
            by_class[failure_class.value] += 1
            if failure_class is FailureClass.HARD_DECLINE and demo_order_id is None:
                demo_order_id = order_id

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        if demo_order_id is not None:
            conn.execute(
                text(
                    "UPDATE cases SET demo_loose_prompt = true WHERE razorpay_order_id = :order_id"
                ),
                {"order_id": demo_order_id},
            )
        rows = conn.execute(text("SELECT arm, count(*) FROM cases GROUP BY arm ORDER BY arm")).all()
        conn.commit()
    engine.dispose()

    print(f"seeded {sum(by_class.values())}/{args.count} cases ({failures} failed)")
    print(f"by class: {dict(by_class)}")
    print(f"by arm (all cases in DB, not just this batch): {dict(rows)}")
    if demo_order_id is None:
        print(
            "WARNING: no HARD_DECLINE case was seeded; the 3:00 demo beat has nothing to fire on."
        )
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
