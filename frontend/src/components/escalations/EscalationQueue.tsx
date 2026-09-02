// Human review queue.
//
// Each item names the rule_id that stopped the agent. "Compliant escalation"
// is a judged criterion, and an escalation without a stated cause is just a
// stuck case.
//
// Resolving records a human decision; it does not resume the agent. A case
// that hit a stopping rule stays stopped — make that explicit in the UI copy
// so it doesn't read as a broken button.
//
// The rule summary across the top is display-only: it counts the items
// already in the list and reorders nothing. When one rule is stopping
// dozens of cases, that is the thing an operator needs to see first — the
// queue is a symptom, the rule is the cause.

import { useEffect, useRef, useState } from 'react'
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

  // Closing the form unmounts the control the keyboard was on, which drops
  // focus to <body>. On a queue this long that means being thrown back to the
  // top of the page, so hand focus back to the button that opened the form.
  // The ref guard keeps this from stealing focus on first mount.
  const triggerRef = useRef<HTMLButtonElement>(null)
  const returnFocus = useRef(false)

  useEffect(() => {
    if (!open && returnFocus.current) {
      returnFocus.current = false
      triggerRef.current?.focus()
    }
  }, [open])

  function close() {
    returnFocus.current = true
    setOpen(false)
  }

  const resolve = useMutation({
    mutationFn: (note: string) => api.resolveEscalation(caseId, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['escalations'] })
      close()
      setNote('')
    },
  })

  if (!open) {
    return (
      <button ref={triggerRef} className="btn" onClick={() => setOpen(true)}>
        Record decision
      </button>
    )
  }

  return (
    <form
      className="resolve-form"
      onSubmit={(e) => {
        e.preventDefault()
        if (note.trim()) resolve.mutate(note.trim())
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') close()
      }}
    >
      <label className="field">
        <span className="field-label">Decision note</span>
        <input
          className="input"
          autoFocus
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What did you do about this case?"
        />
      </label>
      <button type="submit" className="btn btn-primary" disabled={resolve.isPending}>
        {resolve.isPending ? 'Saving…' : 'Save'}
      </button>
      <button type="button" className="btn" onClick={close}>
        Cancel
      </button>
      {/* A failed write must say so — otherwise the form just sits there and
       * the operator assumes the decision was recorded. */}
      {resolve.isError && (
        <p role="alert" style={{ color: 'var(--danger)', margin: 0, width: '100%' }}>
          Could not record that decision. Nothing was saved — try again.
        </p>
      )}
    </form>
  )
}

/** Counts per rule_id, most common first. Derived from `items` only. */
function ruleSummary(items: EscalationItem[]): [string, number][] {
  const counts = new Map<string, number>()
  for (const item of items) {
    counts.set(item.ruleId, (counts.get(item.ruleId) ?? 0) + 1)
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])
}

export function EscalationQueue({ items }: { items: EscalationItem[] }) {
  if (items.length === 0) {
    return <p className="muted">No open escalations.</p>
  }

  const summary = ruleSummary(items)

  return (
    <div className="stack">
      <div className="notice">
        Resolving records your decision on the case's audit trail. It does not resume the agent —
        a case that hit a stopping rule stays stopped.
      </div>

      {summary.length > 0 && (
        <div className="chip-row">
          {summary.map(([ruleId, count]) => (
            <span key={ruleId} className="chip">
              <span className="chip-count">{count}</span>
              <span className="mono muted">{ruleId}</span>
            </span>
          ))}
        </div>
      )}

      {items.map((item) => (
        <article key={item.case.id} className="card stack-tight">
          <div className="row-between">
            <div>
              <Link to={`/cases/${item.case.id}`} className="link-id">
                {item.case.orderId}
              </Link>
              <span className="muted" style={{ marginLeft: 'var(--space-3)' }}>
                {formatPaise(item.case.amountPaise)} · escalated {formatIST(item.escalatedAt)}
              </span>
            </div>
            <PolicyVerdictBadge decision={item.blockedDecision} ruleId={item.ruleId} />
          </div>
          <p style={{ margin: 0, color: 'var(--ink-soft)' }}>{item.reason}</p>
          <div style={{ marginTop: 'var(--space-2)' }}>
            <ResolveForm caseId={item.case.id} />
          </div>
        </article>
      ))}
    </div>
  )
}
