// App bar + primary nav + content column + footer.
//
// One black bar across the top, as on razorpay.com: brand mark on the left,
// the five text links beside it, the live pipeline-status pill on the right.
// Below 760px the links drop to their own scrollable row under the brand
// (see .appbar / .topnav in styles/index.css). Presentation lives in CSS
// rather than inline styles so the breakpoint can restyle the same markup.
//
// Nav: Dashboard, Cases, Escalations, Demo, Test payment. Text only —
// razorpay.com's nav carries no icons, and the escalations item's count
// badge is the one glyph that earns its place: an unattended human queue is
// a visible failure state, not a hidden one. "Test payment" sits last, next
// to Demo, because both are operator tools rather than views of the data;
// `end: false` so /pay/return keeps it highlighted while the payer is
// coming back.
//
// The pipeline-status pill answers a different question than that badge:
// the badge says "N cases need a human"; the pill says "is the automated
// pipeline itself healthy". Both are derived from the same `listEscalations`
// poll this component already owns — no separate endpoint — by checking for
// the `DIAGNOSIS_FAILED` rule, which is what an LLM-provider outage looks
// like in this data (see CaseTimeline's `llm_rejected` handling for the same
// failure surfacing per-case). A dashboard reading gross ₹0 is easy to
// misread as "no failures happened today"; this pill is the honest version,
// visible on every page.

import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/cases', label: 'Cases', end: false },
  { to: '/escalations', label: 'Escalations', end: false },
  { to: '/demo', label: 'Demo', end: false },
  { to: '/pay', label: 'Test payment', end: false },
] as const

/** The brand glyph: a leaning slash in the beam blues, the same "/" the
 * page's light beams and Razorpay's own mark lean at. Decorative — the
 * wordmark beside it carries the name. Gradient stops take their colours
 * via `style`, not the `stop-color` attribute: presentation attributes do
 * not resolve `var()`. */
function BrandMark() {
  return (
    <svg width="16" height="20" viewBox="0 0 16 20" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="brand-beam" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" style={{ stopColor: 'var(--beam)' }} />
          <stop offset="1" style={{ stopColor: 'var(--brand)' }} />
        </linearGradient>
      </defs>
      <path d="M10 0h6L6 20H0z" fill="url(#brand-beam)" />
    </svg>
  )
}

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
        {/* A plain Link, not a NavLink: the brand is a way home, not a
         * fifth nav item, and must not pick up aria-current on the
         * dashboard. */}
        <Link to="/" className="brand" aria-label="Recoup — dashboard">
          <BrandMark />
          <span className="brand-mark">Recoup</span>
          <span className="brand-sub">payment recovery</span>
        </Link>

        {/* NavLink sets aria-current="page" on the active route itself; the
         * active styling keys off that attribute rather than a class, so the
         * visual state and the announced state cannot drift apart. */}
        <nav className="topnav" aria-label="Primary">
          {NAV.map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} className="nav-item">
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
        </nav>

        <div className="appbar-right">
          <PipelineStatus diagnosisFailedCount={diagnosisFailedCount} />
        </div>
      </header>

      <main className="content">{children}</main>

      <footer className="foot">
        <span className="dot" aria-hidden="true" />
        <span>The LLM proposes, the policy gate disposes</span>
      </footer>
    </div>
  )
}
