// Sidebar navigation + content area.
//
// Nav: Dashboard, Cases, Escalations, Demo. The escalations item carries a
// count badge — an unattended human queue is a visible failure state, not a
// hidden one.

import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/cases', label: 'Cases', end: false },
  { to: '/escalations', label: 'Escalations', end: false },
  { to: '/demo', label: 'Demo', end: false },
] as const

export function AppShell({ children }: { children: ReactNode }) {
  const { data: escalations } = useQuery({
    queryKey: ['escalations'],
    queryFn: api.listEscalations,
    refetchInterval: 10_000,
  })
  const openCount = escalations?.length ?? 0

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <nav
        style={{
          width: 200,
          flexShrink: 0,
          borderRight: '1px solid var(--line)',
          padding: '1.5rem 1rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.25rem',
        }}
      >
        <div style={{ fontWeight: 700, fontSize: '1.1rem', marginBottom: '1.5rem' }}>Recoup</div>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            style={({ isActive }) => ({
              padding: '0.5rem 0.6rem',
              borderRadius: 8,
              textDecoration: 'none',
              color: isActive ? 'var(--ink)' : 'var(--muted)',
              background: isActive ? 'var(--surface)' : 'transparent',
              fontWeight: isActive ? 600 : 400,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            })}
          >
            {item.label}
            {item.to === '/escalations' && openCount > 0 && (
              <span
                className="badge"
                style={{ background: 'var(--warn-weak)', color: 'var(--warn)' }}
              >
                {openCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
      <main style={{ flex: 1, padding: '2rem', maxWidth: 1100 }}>{children}</main>
    </div>
  )
}
