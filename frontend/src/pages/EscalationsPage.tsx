// Human review queue — cases where the agent correctly stopped.

import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { ErrorNote, Loading } from '@/components/PageState'
import { EscalationQueue } from '@/components/escalations/EscalationQueue'

export default function EscalationsPage() {
  const { data: items, isLoading, error } = useQuery({
    queryKey: ['escalations'],
    queryFn: api.listEscalations,
  })

  return (
    <div>
      <header className="page-head">
        <h1 className="page-title">Escalations</h1>
        <p className="page-sub">
          Cases where the agent stopped on purpose — a stopping rule fired, so it went silent and
          handed the case to a human instead of spending an attempt.
        </p>
      </header>

      {isLoading && <Loading what="escalations" />}
      {error && <ErrorNote>Could not load escalations.</ErrorNote>}
      {items && <EscalationQueue items={items} />}
    </div>
  )
}
