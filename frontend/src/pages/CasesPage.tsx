// Case list with filters for arm, status and failure class.
//
// The arm filter matters for the demo: switching to "control" shows a set of
// cases with an empty action history, which is the fastest way to make the
// holdout concrete to someone watching.
//
// Each filter carries a visible label rather than leaning on its "All …"
// option to name the field — once a filter is set, a placeholder-as-label
// is gone exactly when the reader needs to know what the control is.

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { ErrorNote, Loading } from '@/components/PageState'
import { CaseTable } from '@/components/cases/CaseTable'
import { FAILURE_CLASSES } from '@/api/types'
import { FAILURE_CLASS_LABEL, STATUS_LABEL } from '@/lib/constants'

const STATUSES = [
  'open',
  'scheduled',
  'awaiting_customer',
  'recovered',
  'escalated',
  'exhausted',
  'control_observed',
]

function Field({
  label,
  value,
  onChange,
  children,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  children: React.ReactNode
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <select className="select" value={value} onChange={(e) => onChange(e.target.value)}>
        {children}
      </select>
    </label>
  )
}

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
      <header className="page-head">
        <h1 className="page-title">Cases</h1>
        <p className="page-sub">
          Every failed payment the agent has seen. Filter to the control arm to see the holdout:
          same failures, no action ever taken.
        </p>
      </header>

      <div className="filter-bar">
        <Field label="Arm" value={arm} onChange={setArm}>
          <option value="">All arms</option>
          <option value="treatment">Treatment</option>
          <option value="control">Control (held out)</option>
        </Field>

        <Field label="Status" value={status} onChange={setStatus}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s] ?? s}
            </option>
          ))}
        </Field>

        <Field label="Failure class" value={failureClass} onChange={setFailureClass}>
          <option value="">All classes</option>
          {FAILURE_CLASSES.map((fc) => (
            <option key={fc} value={fc}>
              {FAILURE_CLASS_LABEL[fc]}
            </option>
          ))}
        </Field>

        {cases && (
          <span className="result-count" role="status">
            {cases.length} case{cases.length === 1 ? '' : 's'}
          </span>
        )}
      </div>

      {isLoading && <Loading what="cases" />}
      {error && <ErrorNote>Could not load cases.</ErrorNote>}
      {cases && <CaseTable cases={cases} />}
    </div>
  )
}
