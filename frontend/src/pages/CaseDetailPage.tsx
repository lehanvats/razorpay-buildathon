// One case: header facts plus the full audit timeline.
//
// The explainability view. Deep-linkable by case id so the demo can jump
// straight to the seeded HARD_DECLINE case where the gate blocks a retry.
//
// Facts sit in a narrow rail beside the timeline at >=720px, rather than a
// full-width card stacked above it — the facts are reference data the
// reader checks against, not the thing they came to read; a two-column
// layout lets both stay on screen together on anything but a phone.
// Deliberately NOT adding a second, derived summary of case state (e.g. a
// stepper across the top) above this: CaseTimeline already IS that
// summary, in full, and a second hand-built mapping from 15 event types to
// N stepper stages is a second place for that mapping to be wrong — the
// exact failure mode this file's own event-order and reasoning-verbatim
// rules exist to prevent.

import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { ErrorNote, Loading } from '@/components/PageState'
import { StatusBadge, ToneBadge } from '@/components/Tone'
import { IconArrowLeft } from '@/components/icons'
import { CaseTimeline } from '@/components/cases/CaseTimeline'
import { FAILURE_CLASS_HINT, FAILURE_CLASS_LABEL } from '@/lib/constants'
import { formatIST, formatPaise } from '@/lib/format'

export default function CaseDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data: detail, isLoading, error } = useQuery({
    queryKey: ['case', id],
    queryFn: () => api.getCase(id!),
    enabled: !!id,
  })

  if (isLoading) return <Loading what="this case" />
  if (error || !detail) return <ErrorNote>Case not found.</ErrorNote>

  const isControl = detail.arm === 'control'

  return (
    <div className="stack">
      <Link to="/cases" className="back-link">
        <IconArrowLeft size={14} />
        back to cases
      </Link>

      <div className="case-detail-layout">
        <aside className={`card stack-tight case-facts-rail${isControl ? ' card--control' : ''}`}>
          <h1 className="mono" style={{ fontSize: 'var(--text-lg)', letterSpacing: '-0.01em' }}>
            {detail.orderId}
          </h1>
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', flexWrap: 'wrap' }}>
            {isControl && <ToneBadge tone="control">held out — no action ever taken</ToneBadge>}
            <StatusBadge status={detail.status} />
          </div>

          {/* The class hint is the strategy for this failure, stated where
           * the class is named — it is the reason the rest of the timeline
           * looks the way it does. */}
          <p className="stat-note">{FAILURE_CLASS_HINT[detail.failureClass]}</p>

          <div className="facts">
            <Fact label="Class" value={FAILURE_CLASS_LABEL[detail.failureClass]} />
            <Fact label="Arm" value={isControl ? 'Control (held out)' : 'Treatment'} />
            <Fact label="Method" value={detail.method} mono />
            <Fact label="Amount" value={formatPaise(detail.amountPaise)} mono />
            <Fact
              label="Recovered"
              value={
                detail.recoveredAmountPaise != null
                  ? formatPaise(detail.recoveredAmountPaise)
                  : '—'
              }
              mono
              accent={detail.recoveredAmountPaise != null}
            />
            <Fact label="Attempts used" value={String(detail.attemptsUsed)} mono />
            <Fact label="Opened" value={formatIST(detail.createdAt)} />
          </div>
        </aside>

        <section className="card case-timeline-col">
          <h2 className="card-title" style={{ marginBottom: 'var(--space-5)' }}>
            Audit trail
          </h2>
          <CaseTimeline entries={detail.timeline} />
        </section>
      </div>
    </div>
  )
}

function Fact({
  label,
  value,
  mono,
  accent,
}: {
  label: string
  value: string
  mono?: boolean
  accent?: boolean
}) {
  return (
    <div>
      <div className="fact-label">{label}</div>
      <div className={mono ? 'mono' : undefined} style={accent ? { color: 'var(--accent)' } : undefined}>
        {value}
      </div>
    </div>
  )
}
