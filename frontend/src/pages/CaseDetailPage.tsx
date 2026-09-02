// One case: header facts plus the full audit timeline.
//
// The explainability view. Deep-linkable by case id so the demo can jump
// straight to the seeded HARD_DECLINE case where the gate blocks a retry.

import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { CaseTimeline } from '@/components/cases/CaseTimeline'
import { FAILURE_CLASS_LABEL } from '@/lib/constants'
import { formatIST, formatPaise } from '@/lib/format'

export default function CaseDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data: detail, isLoading, error } = useQuery({
    queryKey: ['case', id],
    queryFn: () => api.getCase(id!),
    enabled: !!id,
  })

  if (isLoading) return <p className="muted">Loading…</p>
  if (error || !detail) return <p style={{ color: 'var(--danger)' }}>Case not found.</p>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      <Link to="/cases" className="muted">
        &larr; back to cases
      </Link>

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <h1 style={{ fontSize: '1.3rem', margin: 0 }} className="mono">
            {detail.orderId}
          </h1>
          <span className="mono muted">{detail.status}</span>
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: '1rem',
            marginTop: '1rem',
          }}
        >
          <Field label="Class" value={FAILURE_CLASS_LABEL[detail.failureClass]} />
          <Field label="Arm" value={detail.arm === 'control' ? 'Control (held out)' : 'Treatment'} />
          <Field label="Amount" value={formatPaise(detail.amountPaise)} />
          <Field
            label="Recovered"
            value={detail.recoveredAmountPaise != null ? formatPaise(detail.recoveredAmountPaise) : '—'}
          />
          <Field label="Method" value={detail.method} />
          <Field label="Attempts used" value={String(detail.attemptsUsed)} />
          <Field label="Opened" value={formatIST(detail.createdAt)} />
        </div>
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Audit trail</div>
        <CaseTimeline entries={detail.timeline} />
      </div>
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="muted" style={{ fontSize: '0.75rem' }}>
        {label}
      </div>
      <div>{value}</div>
    </div>
  )
}
