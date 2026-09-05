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
//
// The rail is presentation only. Every entry the API sends gets a node,
// including ones with no icon or tone of their own.

import type { EventType, TimelineEntry } from '@/api/types'
import { IconBlock, IconCheck, IconClock, IconEscalation } from '@/components/icons'
import { PolicyVerdictBadge } from '@/components/cases/PolicyVerdictBadge'
import type { Tone } from '@/lib/constants'
import { formatIST, formatPaise } from '@/lib/format'

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
  operator_proposed: 'Operator proposed',
  payment_verified: 'Payment verified with Razorpay',
}

/** Tone per event. Anything not listed stays neutral — a new backend event
 * renders as a plain node rather than disappearing. */
const EVENT_TONE: Partial<Record<EventType, Tone>> = {
  policy_approved: 'accent',
  action_completed: 'accent',
  recovered: 'accent',
  policy_blocked: 'danger',
  llm_rejected: 'danger',
  action_failed: 'danger',
  escalated: 'warn',
  escalation_resolved: 'warn',
  action_scheduled: 'control',
  payment_verified: 'accent',
}

const EVENT_ICON: Partial<Record<EventType, () => JSX.Element>> = {
  policy_approved: () => <IconCheck size={13} />,
  action_completed: () => <IconCheck size={13} />,
  recovered: () => <IconCheck size={13} />,
  policy_blocked: () => <IconBlock size={13} />,
  llm_rejected: () => <IconBlock size={13} />,
  action_failed: () => <IconBlock size={13} />,
  escalated: () => <IconEscalation size={13} />,
  action_scheduled: () => <IconClock size={13} />,
  payment_verified: () => <IconCheck size={13} />,
}

function nodeStyle(tone: Tone | undefined): React.CSSProperties {
  if (!tone || tone === 'neutral') return {}
  return { background: `var(--${tone}-weak)`, color: `var(--${tone}-ink)` }
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
          <p className="tl-reasoning">{payload.reason}</p>
        )}
      </>
    )
  }
  if (
    (eventType === 'llm_proposed' || eventType === 'operator_proposed') &&
    typeof payload.reasoning === 'string'
  ) {
    // Rule 1: verbatim, never truncated. Same treatment whoever proposed:
    // the gate's verdict follows either way, and the reader should judge
    // the reasoning, not the author.
    return <p className="tl-reasoning">{payload.reasoning}</p>
  }
  if (eventType === 'payment_verified') {
    // The ids are what an operator would paste into the Razorpay dashboard
    // to check this for themselves — so they are shown, in mono, not hidden.
    const linkId = typeof payload.payment_link_id === 'string' ? payload.payment_link_id : null
    const paymentId = typeof payload.payment_id === 'string' ? payload.payment_id : null
    return (
      <p className="tl-reasoning mono" style={{ overflowWrap: 'anywhere' }}>
        {[linkId, paymentId].filter(Boolean).join(' · ')}
        {payload.signature_valid === true && ' · callback signature valid'}
      </p>
    )
  }
  if (eventType === 'llm_rejected' && typeof payload.error === 'string') {
    return (
      <p className="tl-reasoning mono" style={{ color: 'var(--danger)' }}>
        {payload.error}
      </p>
    )
  }
  if (eventType === 'recovered' && typeof payload.amount_paise === 'number') {
    return (
      <p style={{ margin: 'var(--space-1) 0 0', color: 'var(--accent)', fontWeight: 600 }}>
        {formatPaise(payload.amount_paise)}
      </p>
    )
  }
  if (eventType === 'escalation_resolved' && typeof payload.note === 'string') {
    return <p className="tl-reasoning">{payload.note}</p>
  }
  return null
}

export function CaseTimeline({ entries }: { entries: TimelineEntry[] }) {
  if (entries.length === 0) {
    return <p className="muted">No events yet.</p>
  }

  return (
    <ol className="timeline">
      {entries.map((entry, i) => {
        const tone = EVENT_TONE[entry.eventType]
        const Icon = EVENT_ICON[entry.eventType]
        return (
          <li key={`${entry.ts}-${i}`} className="tl-item">
            <time className="tl-time" dateTime={entry.ts}>
              {formatIST(entry.ts)}
            </time>
            <div className="tl-rail">
              <span className="tl-node" style={nodeStyle(tone)}>
                {/* Events with no tone of their own get a plain mark, in the
                  * node's inherited colour — not the sidebar's accent .dot. */}
                {Icon ? (
                  <Icon />
                ) : (
                  <span
                    aria-hidden="true"
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      background: 'currentColor',
                    }}
                  />
                )}
              </span>
            </div>
            <div className="tl-body">
              <div className="tl-head">
                {/* Falls back to the raw event type, matching EVENT_TONE and
                  * EVENT_ICON: an event the backend adds before the frontend
                  * knows about it should read as an unstyled but named node,
                  * not as a correctly-drawn node with an empty label. */}
                <span className="tl-event">
                  {EVENT_LABEL[entry.eventType] ?? entry.eventType}
                </span>
                <span className="tl-actor">{entry.actor}</span>
              </div>
              <EntryDetail entry={entry} />
            </div>
          </li>
        )
      })}
    </ol>
  )
}
