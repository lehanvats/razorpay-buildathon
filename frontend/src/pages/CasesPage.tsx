// Case list with filters for arm, status and failure class.
//
// This is also the master-detail layout for /cases/:id: at >=1100px this
// component's list pane docks beside <Outlet/> (CaseDetailPage or the
// empty-state hint below), so opening a case keeps the filters and scroll
// position intact instead of navigating away from them. Below 1100px there
// is no room for two panes — the list pane hides itself via CSS the moment
// a case is selected (see `hasSelection` / .cases-list-pane--collapsed),
// and CaseDetailPage renders full-width exactly as it always has. Deep
// links to /cases/:id and the back button both still work unchanged in
// either layout — nothing here reaches for that state, it falls out of
// plain nested routing.
//
// The arm filter matters for the demo: switching to "control" shows a set of
// cases with an empty action history, which is the fastest way to make the
// holdout concrete to someone watching.
//
// Each filter carries a visible label rather than leaning on its "All …"
// option to name the field — once a filter is set, a placeholder-as-label
// is gone exactly when the reader needs to know what the control is.

import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
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

/** The detail pane's resting state — nothing selected yet. Only ever visible
 * at >=1100px, docked beside the list; CSS hides it below that, where an
 * unselected list needs the full width for itself. */
function CasesEmptyHint() {
  return (
    <div className="card cases-empty-hint">
      <p className="muted" style={{ margin: 0 }}>
        Select a case to see its audit trail.
      </p>
    </div>
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

  // True the instant the route is /cases/<something> rather than bare
  // /cases — cheaper and just as correct as matching the child route's own
  // :id param, which isn't visible to a parent layout via useParams().
  const hasSelection = useLocation().pathname !== '/cases'

  return (
    <div className="cases-layout">
      <div className={`cases-list-pane${hasSelection ? ' cases-list-pane--collapsed' : ''}`}>
        <header className="page-head">
          <h1 className="page-title">Cases</h1>
          <p className="page-sub">
            Every failed payment the agent has seen. Filter to the control arm to see the
            holdout: same failures, no action ever taken.
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

      <div className={`cases-detail-pane${hasSelection ? '' : ' cases-detail-pane--collapsed'}`}>
        <Outlet />
      </div>
    </div>
  )
}

export { CasesEmptyHint }
