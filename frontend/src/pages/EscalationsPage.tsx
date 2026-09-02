// Human review queue — cases where the agent correctly stopped.

import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { EscalationQueue } from '@/components/escalations/EscalationQueue'

export default function EscalationsPage() {
  const { data: items, isLoading, error } = useQuery({
    queryKey: ['escalations'],
    queryFn: api.listEscalations,
  })

  return (
    <div>
      <h1 style={{ fontSize: '1.4rem', marginBottom: '1rem' }}>Escalations</h1>
      {isLoading && <p className="muted">Loading…</p>}
      {error && <p style={{ color: 'var(--danger)' }}>Could not load escalations.</p>}
      {items && <EscalationQueue items={items} />}
    </div>
  )
}
