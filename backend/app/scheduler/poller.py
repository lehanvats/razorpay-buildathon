"""The one scheduler implementation: claim due actions, dispatch, repeat.

Runs as a separate process (`python -m app.scheduler.poller`) alongside the
API, or as a periodic invocation on a host that offers one. Stateless — all
state is the `actions` table — so it can be restarted or run redundantly.

Claiming must be atomic. Two pollers, or one poller restarted mid-batch,
must never dispatch the same action twice:

    UPDATE actions SET claimed_at = now()
    WHERE id IN (
        SELECT id FROM actions
        WHERE executed_at IS NULL AND claimed_at IS NULL
          AND scheduled_for <= now()
        ORDER BY scheduled_for
        LIMIT :batch
        FOR UPDATE SKIP LOCKED
    ) RETURNING id

`FOR UPDATE SKIP LOCKED` is the whole trick; without it the double-charge
risk is real rather than theoretical.
"""

from typing import Any

POLL_INTERVAL_SECONDS = 30
BATCH_SIZE = 25

MAX_ATTEMPTS_PER_ACTION = 3
"""Dispatch attempts — distinct from the NPCI *charge* attempt budget. This
counts transport failures (Razorpay 5xx, timeouts). A dispatch that never
reached Razorpay must not consume a regulatory retry; see
executors/retry.py for where the charge counter is incremented."""


def claim_due_actions(session: Any, limit: int = BATCH_SIZE) -> list[Any]:
    """Atomically claim up to `limit` actions whose time has come."""
    raise NotImplementedError("step-06: scheduler poller")


def dispatch(session: Any, action: Any) -> None:
    """Route one claimed action to its executor.

    Re-checks the case is still open before executing: a case that recovered
    on its own since scheduling must have its pending retry dropped, not run.
    """
    raise NotImplementedError("step-06: scheduler poller")


def run_forever() -> None:
    """Poll loop. Entry point for `python -m app.scheduler.poller`."""
    raise NotImplementedError("step-06: scheduler poller")


if __name__ == "__main__":
    run_forever()
