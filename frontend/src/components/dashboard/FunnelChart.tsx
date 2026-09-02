// failed -> eligible -> treated -> recovered.
//
// `eligible` excludes hard declines. Label that on the chart itself — an
// unexplained drop between failed and eligible reads as attrition when it is
// actually us correctly refusing to chase unrecoverable payments.

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
    <div className="card">
      <div style={{ fontWeight: 600, marginBottom: '1rem' }}>Funnel</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
        {STAGES.map((stage) => {
          const value = funnel[stage.key]
          const width = max > 0 ? (value / max) * 100 : 0
          return (
            <div key={stage.key}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: '0.85rem',
                  marginBottom: '0.2rem',
                }}
              >
                <span>
                  {stage.label}
                  {stage.hint && <span className="muted"> — {stage.hint}</span>}
                </span>
                <span className="mono">{value}</span>
              </div>
              <div style={{ background: 'var(--line)', borderRadius: 6, height: 10 }}>
                <div
                  style={{
                    width: `${width}%`,
                    background: 'var(--accent)',
                    height: '100%',
                    borderRadius: 6,
                    transition: 'width 300ms ease',
                  }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
