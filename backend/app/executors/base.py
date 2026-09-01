"""Executor contract.

Every executor takes a **Verdict**, never a Proposal. That type signature is
how "the LLM proposes, the policy gate disposes" is enforced at the call site
rather than by convention — there is no way to hand an executor an
unapproved suggestion without deliberately constructing a fake verdict.

Every executor writes an audit event before acting and after acting. An
executor that can act silently is a bug. `core/audit.py` doesn't exist until
step-07, so the actual `audit.record` calls below are TODO(step-07) markers
rather than real calls — the same deferral pattern every step-06 call site in
`services/case_manager.py` already uses. `with_audit` still does its real job
today: it is the single seam every executor's `execute` passes through, so
wiring the audit calls in step-07 is a one-file change, not a per-executor one.
"""

from dataclasses import dataclass
from functools import wraps
from typing import Any, Protocol

from app.schemas.proposal import ActionKind, Verdict


@dataclass
class ExecutionResult:
    """Outcome of one execution attempt.

    Persisted onto `actions.result`/`error`/`razorpay_ref` by
    `scheduler.poller.dispatch`, and mirrored into an ACTION_COMPLETED /
    ACTION_FAILED audit event by `with_audit` (TODO(step-07)).
    """

    ok: bool
    razorpay_ref: str | None = None
    detail: str | None = None
    error: str | None = None


class Executor(Protocol):
    """One approved action, performed against the outside world."""

    kind: ActionKind
    """Which action menu entry this executor serves.

    NOT a unique dispatch key — several executors share a `kind`, because one
    approved action can fan out to more than one step:

        SEND_PAYMENT_LINK  -> PaymentLinkExecutor + DunningExecutor
                              (create the link, then email it)
        SCHEDULE_RETRY     -> PreDebitNoticeExecutor + RetryExecutor
                              (notify, wait 24h, then debit)

    So step-06 must build `dict[ActionKind, list[Executor]]` and run the list
    in order — a plain `dict[ActionKind, Executor]` would silently drop the
    dunning email and the pre-debit notice, and losing the notice is a
    compliance breach, not a missing feature.

    In practice PreDebitNoticeExecutor is not in that list — it fires
    eagerly from `scheduler.poller.schedule` at scheduling time (the "first
    leg" of a retry, per its own docstring), not from the deferred dispatch
    list, since the notice must go out now while the debit itself waits for
    `scheduled_for`. See `scheduler/poller.py` for why.

    The alternative — giving each executor its own ActionKind — was rejected
    because it widens the LLM's action menu beyond the four choices it should
    be reasoning about. Composition belongs on our side of the gate.
    """

    def execute(self, session: Any, case_id: str, verdict: Verdict) -> ExecutionResult:
        """Perform the action.

        Must be idempotent per action row: the scheduler may redeliver, and a
        double-charged customer is unrecoverable reputationally. Claim the
        action row (set executed_at) before touching the network — done by
        `scheduler.poller.dispatch`, which holds the Action row this
        Verdict was reconstructed from and calls this method.

        Must not raise: transport and validation failures are reported as
        `ExecutionResult(ok=False, error=...)` so `dispatch()` can apply the
        dispatch-attempt budget uniformly rather than every executor needing
        its own retry/backoff logic.
        """
        ...


def with_audit(fn):
    """Decorator wrapping an executor's `execute` so ACTION_STARTED is
    written before the call and ACTION_COMPLETED / ACTION_FAILED after it.

    Applied to every executor. Wrapping here rather than trusting each
    executor to remember means a new executor is audited by construction —
    once step-07 implements `core/audit.py`, this is the one place that
    needs to change.
    """

    @wraps(fn)
    def wrapper(self, session: Any, case_id: str, verdict: Verdict) -> ExecutionResult:
        # TODO(step-07): audit.record(session, case_id=case_id, actor=Actor.EXECUTOR,
        #   event_type=EventType.ACTION_STARTED, payload={"kind": self.kind.value})
        result = fn(self, session, case_id, verdict)
        # TODO(step-07): audit.record(session, case_id=case_id, actor=Actor.EXECUTOR,
        #   event_type=EventType.ACTION_COMPLETED if result.ok else EventType.ACTION_FAILED,
        #   payload={"razorpay_ref": result.razorpay_ref, "detail": result.detail,
        #            "error": result.error})
        return result

    return wrapper
