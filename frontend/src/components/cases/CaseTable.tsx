// Case list. Filterable by arm, status and failure class.
//
// Control-arm rows are visually distinct and show no actions column — a
// reviewer should be able to see at a glance that nothing was done to them.

import { Link } from 'react-router-dom'

import type { CaseSummary } from '@/api/types'
import { FAILURE_CLASS_LABEL } from '@/lib/constants'
import { formatIST, formatPaise } from '@/lib/format'

export function CaseTable({ cases }: { cases: CaseSummary[] }) {
  if (cases.length === 0) {
    return <p className="muted">No cases match these filters.</p>
  }

  return (
    <table>
      <thead>
        <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--line)' }}>
          <th style={{ padding: '0.5rem' }}>Order</th>
          <th style={{ padding: '0.5rem' }}>Class</th>
          <th style={{ padding: '0.5rem' }}>Arm</th>
          <th style={{ padding: '0.5rem' }}>Status</th>
          <th style={{ padding: '0.5rem', textAlign: 'right' }}>Amount</th>
          <th style={{ padding: '0.5rem', textAlign: 'right' }}>Recovered</th>
          <th style={{ padding: '0.5rem' }}>Opened</th>
        </tr>
      </thead>
      <tbody>
        {cases.map((c) => {
          const isControl = c.arm === 'control'
          return (
            <tr
              key={c.id}
              style={{
                borderBottom: '1px solid var(--line)',
                opacity: isControl ? 0.7 : 1,
              }}
            >
              <td style={{ padding: '0.5rem' }}>
                <Link to={`/cases/${c.id}`} className="mono">
                  {c.orderId}
                </Link>
              </td>
              <td style={{ padding: '0.5rem' }}>{FAILURE_CLASS_LABEL[c.failureClass]}</td>
              <td style={{ padding: '0.5rem' }}>
                {isControl ? (
                  <span
                    className="badge"
                    style={{ background: 'var(--control-weak)', color: 'var(--control)' }}
                  >
                    control — held out
                  </span>
                ) : (
                  'treatment'
                )}
              </td>
              <td style={{ padding: '0.5rem' }} className="mono">
                {c.status}
              </td>
              <td style={{ padding: '0.5rem', textAlign: 'right' }} className="mono">
                {formatPaise(c.amountPaise)}
              </td>
              <td style={{ padding: '0.5rem', textAlign: 'right' }} className="mono">
                {c.recoveredAmountPaise != null ? formatPaise(c.recoveredAmountPaise) : '—'}
              </td>
              <td style={{ padding: '0.5rem' }} className="muted">
                {formatIST(c.createdAt)}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
