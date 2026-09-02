// failed -> eligible -> treated -> recovered.
//
// `eligible` excludes hard declines. Label that on the chart itself — an
// unexplained drop between failed and eligible reads as attrition when it is
// actually us correctly refusing to chase unrecoverable payments.
//
// Each step carries its share of `failed` as well as its count: a step's
// fill bar is only legible relative to the top of the funnel, and showing
// the percentage means the reader does not have to do that division by eye.
//
// Horizontal steps connected by arrows, not stacked bars — a funnel is a
// left-to-right narrowing story, and reading it top-to-bottom (round 1's
// layout) buried that story inside a shape that looks like an unrelated
// stat list. The underlying numbers and hint copy are unchanged.

import type { FunnelCounts } from '@/api/types'

const STAGES: { key: keyof FunnelCounts; label: string; hint?: string }[] = [
  { key: 'failed', label: 'Failed' },
  { key: 'eligible', label: 'Eligible', hint: 'excludes HARD_DECLINE — unrecoverable by design' },
  { key: 'treated', label: 'Treated', hint: 'got at least one scheduled action' },
  { key: 'recovered', label: 'Recovered', hint: 'both arms' },
]

export function FunnelChart({ funnel }: { funnel: FunnelCounts }) {
  const max = Math.max(funnel.failed, 1)

  return (
    <section className="card">
      <h2 className="card-title" style={{ marginBottom: 'var(--space-4)' }}>
        Funnel
      </h2>
      <div className="funnel-flow">
        {STAGES.map((stage, i) => {
          const value = funnel[stage.key]
          const share = (value / max) * 100
          return (
            <div className="funnel-step" key={stage.key}>
              {i > 0 && (
                // Decorative connector between steps — the narrowing is
                // already stated as a percentage, so the arrow carries no
                // information of its own.
                <span className="funnel-arrow" aria-hidden="true">
                  &rarr;
                </span>
              )}
              <div className="funnel-step-body">
                <div className="funnel-step-label">{stage.label}</div>
                <div className="funnel-step-value mono">{value}</div>
                <div className="muted funnel-step-share">{share.toFixed(0)}%</div>
                {/* The bar duplicates a number already printed above it, so
                 * it is decorative to assistive tech rather than a second,
                 * noisier reading of the same value. */}
                <div className="funnel-step-bar" aria-hidden="true">
                  <div className="funnel-step-bar-fill" style={{ width: `${share}%` }} />
                </div>
                {stage.hint && <div className="muted funnel-step-hint">{stage.hint}</div>}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
