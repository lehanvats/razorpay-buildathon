"""Outreach — email the LLM-drafted message.

Also carries the RBI pre-debit notification, which is not marketing but a
regulatory obligation: the customer must be told >= 24h before a mandate
debit. This executor is sometimes running to satisfy a rule rather than to
persuade.

Sending increments `cases.messages_sent` and stamps `last_contact_at`, which
is what the contact-cooldown rule reads on the next pass.
"""

from datetime import UTC, datetime
from typing import Any

from app.db.models import Case
from app.executors.base import ExecutionResult, with_audit
from app.integrations.resend_client import send_email
from app.schemas.proposal import ActionKind, Verdict


class DunningExecutor:
    """Sends the drafted message via Resend (100/day free tier)."""

    kind = ActionKind.SEND_PAYMENT_LINK  # outreach accompanies a link

    @with_audit
    def execute(self, session: Any, case_id: str, verdict: Verdict) -> ExecutionResult:
        """Send the email, then update contact counters in the same transaction.

        The message body is the model's `message_draft`, sent only because a
        verdict approved an outreach action. Never send an unapproved draft,
        and never substitute a hand-written fallback silently — if the draft
        is missing, fail the action so it is visible in the audit trail.
        """
        case = session.get(Case, case_id)
        if case is None:
            return ExecutionResult(ok=False, error=f"case {case_id} not found")
        if not case.customer_email:
            return ExecutionResult(ok=False, error="no customer email on file")
        if not verdict.message_draft:
            return ExecutionResult(ok=False, error="verdict carries no message_draft to send")

        try:
            message_id = send_email(
                case.customer_email, "Complete your payment", verdict.message_draft
            )
        except Exception as exc:  # noqa: BLE001 — reported, not raised; see base.Executor.execute
            return ExecutionResult(ok=False, error=str(exc))

        case.messages_sent += 1
        case.last_contact_at = datetime.now(UTC)
        session.flush()

        return ExecutionResult(ok=True, detail=message_id)


class PreDebitNoticeExecutor:
    """Sends the 24-hour pre-debit notification for mandate retries.

    Separate from DunningExecutor because it is compliance, not persuasion:
    it does NOT count against the 3-message cap and is not subject to the
    24h contact cooldown — this executor deliberately never touches
    `messages_sent` / `last_contact_at`. Conflating the two would let an
    anti-spam rule block a regulatory notice.

    Fired eagerly by `scheduler.poller.schedule` at scheduling time (not
    from the deferred dispatch list): the notice must go out now, while the
    debit itself is what waits for `scheduled_for`. See that module's
    docstring for why this can't be keyed on `verdict.rule_id`.
    """

    kind = ActionKind.SCHEDULE_RETRY  # emitted as the first leg of a retry

    @with_audit
    def execute(self, session: Any, case_id: str, verdict: Verdict) -> ExecutionResult:
        """Notify, stamp `pre_debit_notice_sent_at`, schedule the debit for
        notice + 24h."""
        case = session.get(Case, case_id)
        if case is None:
            return ExecutionResult(ok=False, error=f"case {case_id} not found")
        if not case.customer_email:
            return ExecutionResult(ok=False, error="no customer email on file")

        debit_time = verdict.effective_timing.isoformat() if verdict.effective_timing else "soon"
        body = (
            f"We'll attempt to debit Rs {case.amount_paise / 100:,.2f} from your "
            f"account on or after {debit_time}, per your standing mandate. No "
            "action is needed if this is expected."
        )
        try:
            message_id = send_email(case.customer_email, "Upcoming payment notice", body)
        except Exception as exc:  # noqa: BLE001 — reported, not raised; see base.Executor.execute
            return ExecutionResult(ok=False, error=str(exc))

        case.pre_debit_notice_sent_at = datetime.now(UTC)
        session.flush()

        return ExecutionResult(ok=True, detail=message_id)
