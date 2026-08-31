"""Scheduling interface.

The load-bearing requirement is **durable delay across days**: a SOFT_FUNDS
retry may sleep until the 1st of next month, and a mandate debit must wait
24h after its pre-debit notice. The process that scheduled it will not be
alive then, so the delay cannot live in memory.

The blueprint reaches for Inngest (`step.sleepUntil`) because Vercel Hobby
cron only fires once a day. We express the requirement instead of the vendor:
a due date on the `actions` row, and a poller that claims due rows. That
works on any host, needs no third-party account, and an Inngest adapter drops
in behind this same interface later if the cadence ever needs to be
sub-minute.

Deliberately one implementation, not two — a half-built second scheduler is
worse than none.
"""

from datetime import datetime
from typing import Any, Protocol

from app.schemas.proposal import ActionKind, Verdict


class Scheduler(Protocol):
    """Durable, cross-process delayed execution."""

    def schedule(
        self,
        session: Any,
        *,
        case_id: str,
        kind: ActionKind,
        verdict: Verdict,
        run_at: datetime,
    ) -> str:
        """Persist an action to run at `run_at`. Returns the action id.

        Writes an ACTION_SCHEDULED audit event. `run_at` is the *effective*
        timing from the verdict, not the model's original suggestion — the
        gate may have moved it into the salary window or pushed it past a
        pre-debit notice.
        """
        ...

    def cancel(self, session: Any, action_id: str) -> None:
        """Cancel a not-yet-executed action.

        Needed when a case recovers on its own while a retry is pending —
        charging a customer who already paid is the worst bug this system
        could ship.
        """
        ...
