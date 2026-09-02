// One case: header facts plus the full audit timeline.
//
// The explainability view. Deep-linkable by case id so the demo can jump
// straight to the seeded HARD_DECLINE case where the gate blocks a retry.

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

      <section className={`card stack-tight${isControl ? ' card--control' : ''}`}>
        <div className="row-between">
          <h1 className="mono" style={{ fontSize: 'var(--text-lg)', letterSpacing: '-0.01em' }}>
            {detail.orderId}
          </h1>
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            {isControl && <ToneBadge tone="control">held out — no action ever taken</ToneBadge>}
            <StatusBadge status={detail.status} />
          </div>
        </div>

        {/* The class hint is the strategy for this failure, stated where the
         * class is named — it is the reason the rest of the timeline looks
         * the way it does. */}
        <p className="stat-note">{FAILURE_CLASS_HINT[detail.failureClass]}</p>

        <div className="facts" style={{ marginTop: 'var(--space-3)' }}>
          <Fact label="Class" value={FAILURE_CLASS_LABEL[detail.failureClass]} />
          <Fact label="Arm" value={isControl ? 'Control (held out)' : 'Treatment'} />
          <Fact label="Method" value={detail.method} mono />
          <Fact label="Amount" value={formatPaise(detail.amountPaise)} mono />
          <Fact
            label="Recovered"
            value={
              detail.recoveredAmountPaise != null ? formatPaise(detail.recoveredAmountPaise) : '—'
            }
            mono
            accent={detail.recoveredAmountPaise != null}
          />
          <Fact label="Attempts used" value={String(detail.attemptsUsed)} mono />
          <Fact label="Opened" value={formatIST(detail.createdAt)} />
        </div>
      </section>

      <section className="card">
        <h2 className="card-title" style={{ marginBottom: 'var(--space-5)' }}>
          Audit trail
        </h2>
        <CaseTimeline entries={detail.timeline} />
      </section>
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
