"""Executor contract.

Every executor takes a **Verdict**, never a Proposal. That type signature is
how "the LLM proposes, the policy gate disposes" is enforced at the call site
rather than by convention — there is no way to hand an executor an
unapproved suggestion without deliberately constructing a fake verdict.

Every executor writes an audit event before acting and after acting. An
executor that can act silently is a bug.
"""

from typing import Any, Protocol

from app.schemas.proposal import ActionKind, Verdict


class ExecutionResult:
    """Outcome of one execution attempt.

    Fields: ok, razorpay_ref, detail, error. Persisted onto `actions.result`
    and mirrored into an ACTION_COMPLETED / ACTION_FAILED audit event.
    """

    # TODO(step-06): dataclass fields


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

    The alternative — giving each executor its own ActionKind — was rejected
    because it widens the LLM's action menu beyond the four choices it should
    be reasoning about. Composition belongs on our side of the gate.
    """

    def execute(self, session: Any, case_id: str, verdict: Verdict) -> ExecutionResult:
        """Perform the action.

        Must be idempotent per action row: the scheduler may redeliver, and a
        double-charged customer is unrecoverable reputationally. Claim the
        action row (set executed_at) before touching the network.
        """
        ...


def with_audit(fn):
    """Decorator wrapping an executor so ACTION_STARTED is written before the
    call and ACTION_COMPLETED / ACTION_FAILED after it.

    Applied to every executor. Wrapping here rather than trusting each
    executor to remember means a new executor is audited by construction.
    """
    raise NotImplementedError("step-06: executor audit wrapper")
