// The control-group panel — the differentiator, made visible.
//
// States plainly: N cases held out, untouched, no action ever taken; M of
// them recovered on their own; that self-recovery rate is what treatment is
// measured against.
//
// Include the caveat: with ~100 demo cases a 20% holdout is ~20 control
// cases, so the incremental estimate is noisy. Saying so is the credibility
// move — a judged demo that names its error bars beats one that hides them.
//
// The three figures are pulled out as their own row because they are the
// inputs to the incremental number above; a reader checking that arithmetic
// should not have to find them inside a paragraph.

import type { DashboardMetrics } from '@/api/types'
import { formatPaise, formatRate } from '@/lib/format'

/** The figure is mono (it lines up column-wise with the others and holds
 * still under the 4s refetch); the unit stays in the sans at text weight, so
 * "26 cases" does not render as monospaced prose. */
function Figure({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div>
      <div className="card-title" style={{ marginBottom: 'var(--space-1)' }}>
        {label}
      </div>
      <div style={{ fontSize: 'var(--text-lg)', fontWeight: 600, letterSpacing: '-0.02em' }}>
        <span className="mono">{value}</span>
        {unit && (
          <span
            className="muted"
            style={{ fontSize: 'var(--text-sm)', fontWeight: 400, marginLeft: '0.3em' }}
          >
            {unit}
          </span>
        )}
      </div>
    </div>
  )
}

export function ControlGroupPanel({ metrics }: { metrics: DashboardMetrics }) {
  const { control } = metrics
  const small = control.cases > 0 && control.cases < 30

  return (
    <section className="card card--control stack-tight">
      <h2 className="card-title">The holdout</h2>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 150px), 1fr))',
          gap: 'var(--space-4)',
          padding: 'var(--space-3) 0',
        }}
      >
        <Figure label="Held out" value={String(control.cases)} unit="cases" />
        <Figure label="Self-recovered" value={String(control.recoveredCases)} unit="cases" />
        <Figure label="Baseline rate" value={formatRate(control.recoveryRate)} />
        <Figure label="Value" value={formatPaise(control.recoveredAmountPaise)} />
      </div>

      <p style={{ margin: 0 }}>
        These cases were held out — no retry, no message, no discount, ever. They recovered on
        their own, and that self-recovery rate is exactly what the treatment arm is measured
        against.
      </p>

      {small && (
        <p className="stat-note">
          With only {control.cases} control cases this rate is noisy — treat the incremental
          number as an estimate with real error bars, not a precise figure.
        </p>
      )}
    </section>
  )
}
