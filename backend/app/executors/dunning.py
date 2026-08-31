"""Outreach — email the LLM-drafted message.

Also carries the RBI pre-debit notification, which is not marketing but a
regulatory obligation: the customer must be told >= 24h before a mandate
debit. The policy gate rewrites a premature retry into notice-then-retry, so
this executor is sometimes running to satisfy a rule rather than to persuade.

Sending increments `cases.messages_sent` and stamps `last_contact_at`, which
is what the contact-cooldown rule reads on the next pass.
"""

from typing import Any

from app.executors.base import ExecutionResult
from app.schemas.proposal import ActionKind, Verdict


class DunningExecutor:
    """Sends the drafted message via Resend (100/day free tier)."""

    kind = ActionKind.SEND_PAYMENT_LINK  # outreach accompanies a link

    def execute(self, session: Any, case_id: str, verdict: Verdict) -> ExecutionResult:
        """Send the email, then update contact counters in the same transaction.

        The message body is the model's `message_draft`, sent only because a
        verdict approved an outreach action. Never send an unapproved draft,
        and never substitute a hand-written fallback silently — if the draft
        is missing, fail the action so it is visible in the audit trail.
        """
        raise NotImplementedError("step-06: dunning executor")


class PreDebitNoticeExecutor:
    """Sends the 24-hour pre-debit notification for mandate retries.

    Separate from DunningExecutor because it is compliance, not persuasion:
    it does NOT count against the 3-message cap and is not subject to the
    24h contact cooldown. Conflating the two would let an anti-spam rule
    block a regulatory notice.
    """

    kind = ActionKind.SCHEDULE_RETRY  # emitted as the first leg of a retry

    def execute(self, session: Any, case_id: str, verdict: Verdict) -> ExecutionResult:
        """Notify, stamp `pre_debit_notice_sent_at`, schedule the debit for
        notice + 24h."""
        raise NotImplementedError("step-06: pre-debit notice executor")
