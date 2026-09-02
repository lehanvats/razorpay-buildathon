// The control-group panel — the differentiator, made visible.
//
// States plainly: N cases held out, untouched, no action ever taken; M of
// them recovered on their own; that self-recovery rate is what treatment is
// measured against.
//
// Include the caveat: with ~100 demo cases a 20% holdout is ~20 control
// cases, so the incremental estimate is noisy. Saying so is the credibility
// move — a judged demo that names its error bars beats one that hides them.

import type { DashboardMetrics } from '@/api/types'
import { formatPaise, formatRate } from '@/lib/format'

export function ControlGroupPanel({ metrics }: { metrics: DashboardMetrics }) {
  const { control } = metrics
  const small = control.cases > 0 && control.cases < 30

  return (
    <div className="card" style={{ borderColor: 'var(--control)' }}>
      <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>The holdout</div>
      <p style={{ margin: '0 0 0.75rem' }}>
        <strong>{control.cases}</strong> cases were held out — no retry, no message, no discount,
        ever. <strong>{control.recoveredCases}</strong> of them recovered on their own (
        {formatRate(control.recoveryRate)}, {formatPaise(control.recoveredAmountPaise)}). That
        self-recovery rate is exactly what the treatment arm is measured against.
      </p>
      {small && (
        <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
          With only {control.cases} control cases this rate is noisy — treat the incremental
          number as an estimate with real error bars, not a precise figure.
        </p>
      )}
    </div>
  )
}
