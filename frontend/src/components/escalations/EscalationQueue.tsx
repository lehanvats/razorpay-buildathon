// Human review queue.
//
// Each item names the rule_id that stopped the agent. "Compliant escalation"
// is a judged criterion, and an escalation without a stated cause is just a
// stuck case.
//
// Resolving records a human decision; it does not resume the agent. A case
// that hit a stopping rule stays stopped — make that explicit in the UI copy
// so it doesn't read as a broken button.

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import type { EscalationItem } from '@/api/types'
import { PolicyVerdictBadge } from '@/components/cases/PolicyVerdictBadge'
import { formatIST, formatPaise } from '@/lib/format'

function ResolveForm({ caseId }: { caseId: string }) {
  const [note, setNote] = useState('')
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()

  const resolve = useMutation({
    mutationFn: (note: string) => api.resolveEscalation(caseId, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['escalations'] })
      setOpen(false)
      setNote('')
    },
  })

  if (!open) {
    return (
      <button className="btn" onClick={() => setOpen(true)}>
        Record decision
      </button>
    )
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (note.trim()) resolve.mutate(note.trim())
      }}
      style={{ display: 'flex', gap: '0.5rem' }}
    >
      <input
        autoFocus
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="What did you do about this case?"
        style={{
          flex: 1,
          padding: '0.5rem',
          borderRadius: 8,
          border: '1px solid var(--line)',
          background: 'var(--surface)',
          color: 'var(--ink)',
        }}
      />
      <button type="submit" className="btn btn-primary" disabled={resolve.isPending}>
        Save
      </button>
      <button type="button" className="btn" onClick={() => setOpen(false)}>
        Cancel
      </button>
    </form>
  )
}

export function EscalationQueue({ items }: { items: EscalationItem[] }) {
  if (items.length === 0) {
    return <p className="muted">No open escalations.</p>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
        Resolving records your decision on the case's audit trail. It does not resume the agent —
        a case that hit a stopping rule stays stopped.
      </p>
      {items.map((item) => (
        <div key={item.case.id} className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
            <div>
              <Link to={`/cases/${item.case.id}`} className="mono" style={{ fontWeight: 600 }}>
                {item.case.orderId}
              </Link>
              <span className="muted" style={{ marginLeft: '0.5rem' }}>
                {formatPaise(item.case.amountPaise)} · escalated {formatIST(item.escalatedAt)}
              </span>
            </div>
            <PolicyVerdictBadge decision={item.blockedDecision} ruleId={item.ruleId} />
          </div>
          <p style={{ margin: '0.5rem 0' }}>{item.reason}</p>
          <ResolveForm caseId={item.case.id} />
        </div>
      ))}
    </div>
  )
}
