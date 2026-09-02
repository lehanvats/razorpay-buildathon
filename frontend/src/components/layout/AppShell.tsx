// App bar + nav rail + content area.
//
// Two-tier chrome: a 56px app bar spans the full width and carries the
// brand mark and a live pipeline-status cluster; a nav rail sits below it
// beside the content column. Collapses to a horizontal strip under 900px
// (see .shell / .appbar / .sidebar in styles/index.css). Presentation lives
// in CSS rather than inline styles so the breakpoint can restyle the same
// markup.
//
// Nav: Dashboard, Cases, Escalations, Demo. The escalations item carries a
// count badge — an unattended human queue is a visible failure state, not a
// hidden one.
//
// The app bar's pipeline-status pill answers a different question than that
// badge: the badge says "N cases need a human"; the pill says "is the
// automated pipeline itself healthy". Both are derived from the same
// `listEscalations` poll this component already owns — no separate
// endpoint — by checking for the `DIAGNOSIS_FAILED` rule, which is what an
// LLM-provider outage looks like in this data (see CaseTimeline's
// `llm_rejected` handling for the same failure surfacing per-case). A
// dashboard reading gross ₹0 is easy to misread as "no failures happened
// today"; this pill is the honest version, visible on every page.

import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import {
  IconCases,
  IconDashboard,
  IconDemo,
  IconEscalation,
} from '@/components/icons'

const NAV = [
  { to: '/', label: 'Dashboard', end: true, Icon: IconDashboard },
  { to: '/cases', label: 'Cases', end: false, Icon: IconCases },
  { to: '/escalations', label: 'Escalations', end: false, Icon: IconEscalation },
  { to: '/demo', label: 'Demo', end: false, Icon: IconDemo },
] as const

/** `null` diagnosisFailedCount means "still loading" — distinct from `0`,
 * which means the query resolved and the pipeline really is clean. A
 * loading state that defaulted to 0 would flash a false "nominal" in
 * accent-green for every reader on first paint, which is exactly the kind
 * of false assurance this pill exists to avoid. */
function PipelineStatus({ diagnosisFailedCount }: { diagnosisFailedCount: number | null }) {
  if (diagnosisFailedCount === null) {
    return (
      <span className="badge pipeline-status" style={{ background: 'var(--surface-2)', color: 'var(--muted)' }}>
        <span className="dot" style={{ background: 'currentColor' }} aria-hidden="true" />
        <span>Checking pipeline…</span>
      </span>
    )
  }

  const degraded = diagnosisFailedCount > 0

  return (
    <span
      className="badge pipeline-status"
      style={
        degraded
          ? { background: 'var(--danger-weak)', color: 'var(--danger-ink)' }
          : { background: 'var(--accent-weak)', color: 'var(--accent-ink)' }
      }
      role="status"
      aria-atomic="true"
    >
      <span className="dot" style={{ background: 'currentColor' }} aria-hidden="true" />
      {/* Short label, always: this sits in a fixed-height app bar that must
       * not force horizontal scroll at 375px. The count lives in the title
       * attribute and the sr-only text rather than inline, so the visible
       * label stays a constant width regardless of scheme. */}
      <span title={degraded ? `${diagnosisFailedCount} cases stuck on diagnosis` : undefined}>
        {degraded ? 'LLM diagnosis down' : 'Pipeline nominal'}
      </span>
      {degraded && <span className="sr-only"> — {diagnosisFailedCount} cases affected</span>}
    </span>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  const { data: escalations } = useQuery({
    queryKey: ['escalations'],
    queryFn: api.listEscalations,
    refetchInterval: 10_000,
  })
  const openCount = escalations?.length ?? 0
  const diagnosisFailedCount = escalations
    ? escalations.filter((item) => item.ruleId === 'DIAGNOSIS_FAILED').length
    : null

  return (
    <div className="shell">
      <header className="appbar">
        <div className="brand">
          <span className="brand-mark">Recoup</span>
          <span className="brand-sub">recovery</span>
        </div>
        <PipelineStatus diagnosisFailedCount={diagnosisFailedCount} />
      </header>

      {/* NavLink sets aria-current="page" on the active route itself; the
       * active styling keys off that attribute rather than a class, so the
       * visual state and the announced state cannot drift apart. */}
      <nav className="sidebar" aria-label="Primary">
        <span className="sidebar-eyebrow">Operations</span>

        {NAV.map(({ to, label, end, Icon }) => (
          <NavLink key={to} to={to} end={end} className="nav-item">
            <Icon />
            <span className="nav-label">{label}</span>
            {to === '/escalations' && openCount > 0 && (
              // One atomic status message, not a bare live number: a screen
              // reader announces "3 open escalations", not "3". The count
              // repolls every 10s, so an unlabelled live region would read
              // out a naked digit on every change.
              <span
                className="badge"
                style={{ background: 'var(--warn-weak)', color: 'var(--warn-ink)' }}
                role="status"
                aria-atomic="true"
              >
                {openCount}
                <span className="sr-only"> open escalations</span>
              </span>
            )}
          </NavLink>
        ))}

        <div className="sidebar-foot">
          <span className="dot" aria-hidden="true" />
          <span>The LLM proposes, the policy gate disposes</span>
        </div>
      </nav>

      <main className="content">{children}</main>
    </div>
  )
}
