// failed -> eligible -> treated -> recovered.
//
// `eligible` excludes hard declines. Label that on the chart itself — an
// unexplained drop between failed and eligible reads as attrition when it is
// actually us correctly refusing to chase unrecoverable payments.
//
// Each bar carries its share of `failed` as well as its count: a bar's
// length is only legible relative to the top of the funnel, and showing the
// percentage means the reader does not have to do that division by eye.

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
      <ol className="funnel" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {STAGES.map((stage) => {
          const value = funnel[stage.key]
          const share = (value / max) * 100
          return (
            <li key={stage.key}>
              <div className="funnel-head">
                <span>
                  {stage.label}
                  {stage.hint && <span className="muted"> — {stage.hint}</span>}
                </span>
                <span style={{ whiteSpace: 'nowrap' }}>
                  <span className="funnel-count">{value}</span>
                  {/* Separated by a middot: "100 100%" set as bare adjacent
                    * numbers reads as one malformed figure. */}
                  <span className="muted" style={{ fontSize: 'var(--text-sm)' }}>
                    {' · '}
                    {share.toFixed(0)}%
                  </span>
                </span>
              </div>
              {/* The bar duplicates a number already printed beside it, so it
               * is decorative to assistive tech rather than a second, noisier
               * reading of the same value. */}
              <div className="funnel-track" aria-hidden="true">
                <div className="funnel-fill" style={{ width: `${share}%` }} />
              </div>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
