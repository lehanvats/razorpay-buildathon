// Case list. Filterable by arm, status and failure class.
//
// Control-arm rows are visually distinct and show no actions column — a
// reviewer should be able to see at a glance that nothing was done to them.
//
// "Distinct" is a --control rule down the leading edge plus a faint tint of
// the same hue, never a dimmed row: the holdout is the arm a sceptical
// reader most wants to inspect, so it has to stay at full contrast. The arm
// is also stated in words, so the distinction never rests on colour alone.

import { Link } from 'react-router-dom'

import type { CaseSummary } from '@/api/types'
import { StatusBadge, ToneBadge } from '@/components/Tone'
import { FAILURE_CLASS_LABEL } from '@/lib/constants'
import { formatIST, formatPaise } from '@/lib/format'

export function CaseTable({ cases }: { cases: CaseSummary[] }) {
  if (cases.length === 0) {
    return <p className="muted">No cases match these filters.</p>
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Order</th>
            <th>Class</th>
            <th>Arm</th>
            <th>Status</th>
            <th style={{ textAlign: 'right' }}>Amount</th>
            <th style={{ textAlign: 'right' }}>Recovered</th>
            <th>Opened</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => {
            const isControl = c.arm === 'control'
            return (
              <tr key={c.id} className={isControl ? 'row-control' : undefined}>
                <td>
                  <Link to={`/cases/${c.id}`} className="link-id">
                    {c.orderId}
                  </Link>
                </td>
                <td>{FAILURE_CLASS_LABEL[c.failureClass]}</td>
                <td>
                  {isControl ? (
                    <ToneBadge tone="control">held out</ToneBadge>
                  ) : (
                    <span className="muted">treatment</span>
                  )}
                </td>
                <td>
                  <StatusBadge status={c.status} />
                </td>
                <td className="num">{formatPaise(c.amountPaise)}</td>
                <td className="num">
                  {c.recoveredAmountPaise != null ? (
                    <span style={{ color: 'var(--accent)' }}>
                      {formatPaise(c.recoveredAmountPaise)}
                    </span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td className="muted" style={{ whiteSpace: 'nowrap' }}>
                  {formatIST(c.createdAt)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
