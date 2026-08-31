"""Case lifecycle — where the loop is actually wired together.

This is the one module that knows the whole sequence, so the ordering
constraints that matter live here rather than being spread across routes.

The recovery loop:

    webhook -> open case -> assign arm -> classify
                              |
                     control -+-> observe only, no action, EVER
                              |
                   treatment -+-> diagnose (LLM proposes)
                                    -> gate (policy disposes)
                                        -> approve  -> schedule/execute
                                        -> rewrite  -> schedule amended action
                                        -> block    -> log rule_id, stop
                                        -> escalate -> human queue
                              |
    later webhook (paid) ------+-> write outcome  <-- BOTH arms
"""

from typing import Any


def handle_payment_failed(session: Any, event: dict) -> str:
    """Open a case from a `payment.failed` event and drive the first step.

    Order is load-bearing:
      1. Persist the raw webhook (dedupe on event id) — before anything else,
         so a crash mid-processing is replayable.
      2. Create the case row.
      3. Assign the arm (core.holdout) and write ARM_ASSIGNED.
      4. Classify (core.taxonomy) and write CLASSIFIED.
      5. Only now branch on arm.

    Steps 3-4 happen for control cases too: a control case is *observed*, not
    ignored, and its class is needed to compute per-class control rates.

    Returns:
        The new case id.
    """
    raise NotImplementedError("step-02: case creation")


def advance_case(session: Any, case_id: str) -> None:
    """Run one diagnose -> gate -> act cycle for a treated case.

    Called on case creation and again after any scheduled action completes
    without recovering. Re-entrant and safe to call twice: it no-ops on cases
    that are recovered, escalated or exhausted.

    Refuses to run on control cases — asserts rather than silently returning,
    because a control case reaching this function means the branch above is
    broken and silence would corrupt the headline metric.
    """
    raise NotImplementedError("step-04: agent step orchestration")


def handle_payment_succeeded(session: Any, event: dict) -> None:
    """Close the loop on `payment.captured` / `order.paid` / `payment_link.paid`.

    CRITICAL: this path must NOT short-circuit on `arm == control`.

    Control cases recover on their own — that self-recovery rate is exactly
    what the treatment is measured against. Skipping the outcome write for
    control cases would read as a 0% control rate and make the incremental
    number a lie in our own favour. The holdout gates *actions*, never
    *measurement*.

    Also cancels any pending scheduled action for the case: charging a
    customer who has already paid is the worst bug this system could ship.
    """
    raise NotImplementedError("step-03: outcome recording")


def escalate(session: Any, case_id: str, *, rule_id: str, reason: str) -> None:
    """Move a case to the human queue and silence the agent on it.

    After escalation no further automated action is taken. Silence is the
    correct behaviour under the stopping rule, not a stalled case.
    """
    raise NotImplementedError("step-05: escalation")


def get_timeline(session: Any, case_id: str) -> list[dict]:
    """Read the append-only audit trail for the case-detail view."""
    raise NotImplementedError("step-07: timeline rendering")
