// The headline: two counters, side by side, equal visual weight.
//
//   Gross recovered        what every vendor in this market reports
//   Incremental recovered  treated minus control — what we actually caused
//
// Design intent: do NOT make gross the hero and incremental a footnote. The
// whole pitch is that we publish the smaller, honest number next to the
// flattering one. Equal size, equal prominence, incremental labelled clearly
// as the real figure.
//
// Incremental can be negative. Render that plainly rather than hiding or
// clamping it — a floor would reintroduce exactly the dishonesty the holdout
// exists to prevent.

import type { DashboardMetrics } from '@/api/types'
import { formatPaise, formatRate } from '@/lib/format'

export function RecoveryCounters({ metrics }: { metrics: DashboardMetrics }) {
  const incrementalNegative = metrics.incrementalRecoveredPaise < 0

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
      <div className="card">
        <div className="muted" style={{ fontSize: '0.85rem', marginBottom: '0.4rem' }}>
          Gross recovered
        </div>
        <div style={{ fontSize: '2.25rem', fontWeight: 700 }}>
          {formatPaise(metrics.grossRecoveredPaise)}
        </div>
        <div className="muted" style={{ fontSize: '0.8rem', marginTop: '0.4rem' }}>
          Every rupee recovered on treated cases — what every vendor in this
          market reports.
        </div>
      </div>
      <div className="card" style={{ borderColor: 'var(--control)' }}>
        <div className="muted" style={{ fontSize: '0.85rem', marginBottom: '0.4rem' }}>
          Incremental recovered
        </div>
        <div
          style={{
            fontSize: '2.25rem',
            fontWeight: 700,
            color: incrementalNegative ? 'var(--danger)' : 'var(--ink)',
          }}
        >
          {formatPaise(metrics.incrementalRecoveredPaise, { signed: true })}
        </div>
        <div className="muted" style={{ fontSize: '0.8rem', marginTop: '0.4rem' }}>
          Treatment recovery rate ({formatRate(metrics.treatment.recoveryRate)}) minus control (
          {formatRate(metrics.control.recoveryRate)}), applied to treated volume — what we
          actually caused, not what would have happened anyway.
        </div>
      </div>
    </div>
  )
}
