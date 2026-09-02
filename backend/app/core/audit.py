"""Append-only audit trail.

Every proposal, verdict, action and outcome lands here. This module is the
*only* writer to `audit_events`, and it exposes no update or delete path —
append-only is enforced by the absence of code, not by a comment. Reads go
through services/case_manager.py, which renders the per-case timeline.

An executor that can act without leaving an audit event is a bug. The
convention is: write an event before acting and after acting, so a crash
mid-action shows up as a started-but-unfinished step rather than as nothing
having happened at all.
"""

from enum import StrEnum
from typing import Any

from app.db.models import AuditEvent


class Actor(StrEnum):
    """Who produced the event. Renders as the timeline's left gutter."""

    WEBHOOK = "webhook"
    LLM = "llm"
    POLICY = "policy"
    EXECUTOR = "executor"
    SCHEDULER = "scheduler"
    HUMAN = "human"


class EventType(StrEnum):
    """The timeline vocabulary. Keep it small and stable — the case detail
    view and the demo narration both read these verbatim."""

    WEBHOOK_RECEIVED = "webhook_received"
    CASE_OPENED = "case_opened"
    ARM_ASSIGNED = "arm_assigned"
    CLASSIFIED = "classified"
    LLM_PROPOSED = "llm_proposed"  # payload carries reasoning verbatim
    LLM_REJECTED = "llm_rejected"  # unparseable / schema-invalid output
    POLICY_APPROVED = "policy_approved"  # payload carries rule_id
    POLICY_BLOCKED = "policy_blocked"  # payload carries the blocking rule_id
    ACTION_SCHEDULED = "action_scheduled"
    ACTION_STARTED = "action_started"
    ACTION_COMPLETED = "action_completed"
    ACTION_FAILED = "action_failed"
    ESCALATED = "escalated"
    RECOVERED = "recovered"
    ESCALATION_RESOLVED = "escalation_resolved"  # actor HUMAN; payload carries note


def record(
    session: Any,
    *,
    case_id: str,
    actor: Actor,
    event_type: EventType,
    payload: dict | None = None,
) -> None:
    """Append one immutable event to the trail.

    Args:
        session: active SQLAlchemy session; the caller owns the transaction.
        case_id: the case this event belongs to.
        actor: which component produced it.
        event_type: one of the fixed vocabulary above.
        payload: JSON-serialisable detail. For LLM_PROPOSED this holds the
            model's reasoning paragraph verbatim; for POLICY_BLOCKED it holds
            ``{"rule_id": ...}``. Must never contain API keys or raw PII
            beyond what the case already stores.

    There is intentionally no ``update_event`` or ``delete_event``.
    """
    session.add(
        AuditEvent(
            case_id=case_id,
            actor=actor.value,
            event_type=event_type.value,
            payload_json=payload or {},
        )
    )
    session.flush()
