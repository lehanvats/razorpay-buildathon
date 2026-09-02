// Recovery rate per failure class, treatment arm.
//
// This is where the timing-aware-scheduling claim is evidenced: if
// salary-window scheduling works, SOFT_FUNDS should show the widest gap
// above the dashed control-rate line. If it doesn't, the chart says so —
// which is the point of measuring rather than asserting.
//
// Deliberately NOT a treatment-vs-control pair per class: with a ~20-case
// control arm total, splitting it further by failure class would leave most
// cells at 3-5 cases — a rate computed from that is noise, not signal. The
// single aggregate control rate (dashed line) is the honest comparison
// point; `backend/app/schemas/api.py`'s `by_failure_class` is treatment-arm
// only for the same reason.

import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { DashboardMetrics } from '@/api/types'
import { FAILURE_CLASS_LABEL } from '@/lib/constants'
import { formatRate } from '@/lib/format'

export function ClassBreakdown({ metrics }: { metrics: DashboardMetrics }) {
  const data = Object.entries(metrics.byFailureClass).map(([failureClass, arm]) => ({
    failureClass,
    label: FAILURE_CLASS_LABEL[failureClass as keyof typeof FAILURE_CLASS_LABEL],
    ratePercent: arm ? arm.recoveryRate * 100 : 0,
    cases: arm?.cases ?? 0,
  }))

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
        <div style={{ fontWeight: 600 }}>Recovery rate by failure class (treatment)</div>
        <div className="muted" style={{ fontSize: '0.8rem' }}>
          dashed line = control baseline ({formatRate(metrics.control.recoveryRate)})
        </div>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ left: 0, right: 12 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 12 }} />
          <YAxis tickFormatter={(v) => `${v}%`} tick={{ fontSize: 12 }} width={40} />
          <Tooltip
            formatter={(value: number, _name, item) => [
              `${value.toFixed(1)}% (${item.payload.cases} cases)`,
              'Recovery rate',
            ]}
          />
          <ReferenceLine
            y={metrics.control.recoveryRate * 100}
            stroke="var(--control)"
            strokeDasharray="4 4"
          />
          <Bar dataKey="ratePercent" fill="var(--accent)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
