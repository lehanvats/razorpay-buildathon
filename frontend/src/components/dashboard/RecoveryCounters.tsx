// The headline: two counters, side by side, equal visual weight.
//
//   Gross recovered        what every vendor in this market reports
//   Incremental recovered  treated minus control — what we actually caused
//
// Design intent: do NOT make gross the hero and incremental a footnote. The
// whole pitch is that we publish the smaller, honest number next to the
// flattering one. Equal size, equal prominence, incremental labelled clearly
// as the real figure. The only asymmetry allowed is the --control border and
// tag on the incremental card, which say *where the number comes from*
// rather than making it louder.
//
// Incremental can be negative. Render that plainly rather than hiding or
// clamping it — a floor would reintroduce exactly the dishonesty the holdout
// exists to prevent.

import type { DashboardMetrics } from '@/api/types'
import { formatPaise, formatRate } from '@/lib/format'

export function RecoveryCounters({ metrics }: { metrics: DashboardMetrics }) {
  const incrementalNegative = metrics.incrementalRecoveredPaise < 0

  return (
    <div className="grid-2">
      <section className="card stack-tight">
        <h2 className="card-title">Gross recovered</h2>
        <div className="stat-value">{formatPaise(metrics.grossRecoveredPaise)}</div>
        <p className="stat-note">
          Every rupee recovered on treated cases — what every vendor in this market reports.
        </p>
      </section>

      <section className="card card--control stack-tight">
        <div className="row-between">
          <h2 className="card-title">Incremental recovered</h2>
          <span
            className="badge"
            style={{ background: 'var(--control-weak)', color: 'var(--control-ink)' }}
          >
            measured against a holdout
          </span>
        </div>
        <div
          className="stat-value"
          // Negative is a real, reportable outcome, not an error state — it
          // is coloured to be noticed, never suppressed.
          style={{ color: incrementalNegative ? 'var(--danger)' : 'var(--ink)' }}
        >
          {formatPaise(metrics.incrementalRecoveredPaise, { signed: true })}
        </div>
        <p className="stat-note">
          Treatment recovery rate ({formatRate(metrics.treatment.recoveryRate)}) minus control (
          {formatRate(metrics.control.recoveryRate)}), applied to treated volume — what we
          actually caused, not what would have happened anyway.
        </p>
      </section>
    </div>
  )
}
