// The audit trail, rendered. This is the screen judges read.
//
//   webhook received
//   classified SOFT_FUNDS
//   LLM proposed retry Sep 2, 10:00 IST   <- reasoning shown VERBATIM
//   policy approved (SALARY_WINDOW_RESCHEDULE)
//   pre-debit notice sent
//   retry executed
//   recovered Rs 1,499
//
// Two rules for this component:
//
//  1. Render the model's reasoning paragraph verbatim. Do not truncate it
//     behind a "show more" — the explainability claim is that you can read
//     exactly what the model said and exactly what the policy did about it.
//  2. Never filter or reorder events. A redacted audit trail is not an audit
//     trail. `entries` is rendered in the order the API sends it — already
//     ordered (ts, id) ascending by services/case_manager.get_timeline.

import type { EventType, TimelineEntry } from '@/api/types'
import { PolicyVerdictBadge } from '@/components/cases/PolicyVerdictBadge'
import { formatIST } from '@/lib/format'

const EVENT_LABEL: Record<EventType, string> = {
  webhook_received: 'Webhook received',
  case_opened: 'Case opened',
  arm_assigned: 'Arm assigned',
  classified: 'Classified',
  llm_proposed: 'LLM proposed',
  llm_rejected: 'LLM rejected',
  policy_approved: 'Policy approved',
  policy_blocked: 'Policy blocked',
  action_scheduled: 'Action scheduled',
  action_started: 'Action started',
  action_completed: 'Action completed',
  action_failed: 'Action failed',
  escalated: 'Escalated to human',
  recovered: 'Recovered',
  escalation_resolved: 'Escalation resolved',
}

function EntryDetail({ entry }: { entry: TimelineEntry }) {
  const { eventType, payload, ruleId } = entry

  if (eventType === 'policy_approved' && ruleId) {
    return <PolicyVerdictBadge decision="APPROVE" ruleId={ruleId} />
  }
  if (eventType === 'policy_blocked' && ruleId) {
    return <PolicyVerdictBadge decision="BLOCK" ruleId={ruleId} />
  }
  if (eventType === 'escalated' && ruleId) {
    return (
      <>
        <PolicyVerdictBadge decision="ESCALATE" ruleId={ruleId} />
        {typeof payload.reason === 'string' && (
          <p style={{ margin: '0.4rem 0 0' }}>{payload.reason}</p>
        )}
      </>
    )
  }
  if (eventType === 'llm_proposed' && typeof payload.reasoning === 'string') {
    // Rule 1: verbatim, never truncated.
    return <p style={{ margin: '0.4rem 0 0', whiteSpace: 'pre-wrap' }}>{payload.reasoning}</p>
  }
  if (eventType === 'llm_rejected' && typeof payload.error === 'string') {
    return (
      <p style={{ margin: '0.4rem 0 0', color: 'var(--danger)' }} className="mono">
        {payload.error}
      </p>
    )
  }
  if (eventType === 'recovered' && typeof payload.amount_paise === 'number') {
    return <p style={{ margin: '0.4rem 0 0' }}>Rs {(payload.amount_paise / 100).toLocaleString('en-IN')}</p>
  }
  if (eventType === 'escalation_resolved' && typeof payload.note === 'string') {
    return <p style={{ margin: '0.4rem 0 0' }}>{payload.note}</p>
  }
  return null
}

export function CaseTimeline({ entries }: { entries: TimelineEntry[] }) {
  if (entries.length === 0) {
    return <p className="muted">No events yet.</p>
  }

  return (
    <ol style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {entries.map((entry, i) => (
        <li
          key={`${entry.ts}-${i}`}
          style={{
            display: 'grid',
            gridTemplateColumns: '160px 90px 1fr',
            gap: '0.75rem',
            padding: '0.6rem 0',
            borderBottom: i < entries.length - 1 ? '1px solid var(--line)' : undefined,
          }}
        >
          <span className="muted mono" style={{ fontSize: '0.8rem' }}>
            {formatIST(entry.ts)}
          </span>
          <span className="muted" style={{ fontSize: '0.8rem', textTransform: 'uppercase' }}>
            {entry.actor}
          </span>
          <div>
            <div style={{ fontWeight: 600 }}>{EVENT_LABEL[entry.eventType]}</div>
            <EntryDetail entry={entry} />
          </div>
        </li>
      ))}
    </ol>
  )
}
