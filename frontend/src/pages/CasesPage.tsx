// Case list with filters for arm, status and failure class.
//
// The arm filter matters for the demo: switching to "control" shows a set of
// cases with an empty action history, which is the fastest way to make the
// holdout concrete to someone watching.

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { CaseTable } from '@/components/cases/CaseTable'
import { FAILURE_CLASSES } from '@/api/types'
import { FAILURE_CLASS_LABEL } from '@/lib/constants'

const STATUSES = [
  'open',
  'scheduled',
  'awaiting_customer',
  'recovered',
  'escalated',
  'exhausted',
  'control_observed',
]

export default function CasesPage() {
  const [arm, setArm] = useState<string>('')
  const [status, setStatus] = useState<string>('')
  const [failureClass, setFailureClass] = useState<string>('')

  const { data: cases, isLoading, error } = useQuery({
    queryKey: ['cases', arm, status, failureClass],
    queryFn: () =>
      api.listCases({
        arm: arm || undefined,
        status: status || undefined,
        failureClass: failureClass || undefined,
      }),
  })

  return (
    <div>
      <h1 style={{ fontSize: '1.4rem', marginBottom: '1rem' }}>Cases</h1>
      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem' }}>
        <select value={arm} onChange={(e) => setArm(e.target.value)} className="btn">
          <option value="">All arms</option>
          <option value="treatment">Treatment</option>
          <option value="control">Control (held out)</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="btn">
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={failureClass}
          onChange={(e) => setFailureClass(e.target.value)}
          className="btn"
        >
          <option value="">All classes</option>
          {FAILURE_CLASSES.map((fc) => (
            <option key={fc} value={fc}>
              {FAILURE_CLASS_LABEL[fc]}
            </option>
          ))}
        </select>
      </div>

      {isLoading && <p className="muted">Loading…</p>}
      {error && <p style={{ color: 'var(--danger)' }}>Could not load cases.</p>}
      {cases && <CaseTable cases={cases} />}
    </div>
  )
}
