// Sidebar navigation + content area.
//
// Nav: Dashboard, Cases, Escalations, Demo. The escalations item carries a
// count badge — an unattended human queue is a visible failure state, not a
// hidden one.
//
// Layout is a sticky rail beside a content column, collapsing to a
// horizontal header strip under 900px (see .shell / .sidebar in
// styles/index.css). Presentation lives in CSS rather than inline styles so
// the breakpoint can restyle the same markup.

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

export function AppShell({ children }: { children: ReactNode }) {
  const { data: escalations } = useQuery({
    queryKey: ['escalations'],
    queryFn: api.listEscalations,
    refetchInterval: 10_000,
  })
  const openCount = escalations?.length ?? 0

  return (
    <div className="shell">
      {/* NavLink sets aria-current="page" on the active route itself; the
       * active styling keys off that attribute rather than a class, so the
       * visual state and the announced state cannot drift apart. */}
      <nav className="sidebar" aria-label="Primary">
        <div className="brand">
          <span className="brand-mark">Recoup</span>
          <span className="brand-sub">recovery</span>
        </div>

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
