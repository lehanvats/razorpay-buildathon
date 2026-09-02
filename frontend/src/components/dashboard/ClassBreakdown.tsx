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
//
// One series, so one hue and no legend box — the heading names the series.
// The only other mark is the control baseline, and it is labelled in text
// beside the heading rather than left as a bare dashed line, so the chart
// never asks the reader to decode a colour.

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

interface Datum {
  failureClass: string
  label: string
  ratePercent: number
  cases: number
}

/** Recharts' built-in tooltip is a hard-coded white panel, unreadable on the
 * dark palette. This one is drawn from the same tokens as every other
 * surface, so it inverts with the rest of the app. */
function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: { payload: Datum }[]
}) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="chart-tooltip">
      <div style={{ fontWeight: 600 }}>{d.label}</div>
      <div className="muted">
        {d.ratePercent.toFixed(1)}% recovered · {d.cases} case{d.cases === 1 ? '' : 's'}
      </div>
    </div>
  )
}

export function ClassBreakdown({ metrics }: { metrics: DashboardMetrics }) {
  const data: Datum[] = Object.entries(metrics.byFailureClass).map(([failureClass, arm]) => ({
    failureClass,
    label: FAILURE_CLASS_LABEL[failureClass as keyof typeof FAILURE_CLASS_LABEL],
    ratePercent: arm ? arm.recoveryRate * 100 : 0,
    cases: arm?.cases ?? 0,
  }))

  const axisTick = { fontSize: 12, fill: 'var(--muted)' }

  // An all-zero plot is an empty grid, and an empty grid is indistinguishable
  // from a broken one. Name which zero this is: no cases to measure, or cases
  // measured and none recovered yet. Both are real states of a fresh batch.
  const totalCases = data.reduce((n, d) => n + d.cases, 0)
  const emptyReason =
    totalCases === 0
      ? 'No treated cases yet — seed a batch on the Demo page.'
      : data.every((d) => d.ratePercent === 0)
        ? `No treated case has recovered yet (${totalCases} in flight). The bars fill as outcomes land.`
        : null

  // The y-domain must cover the control baseline, not just the bars.
  // Recharts scales to the data alone, so while treatment recovery sits
  // below the control rate — exactly the case worth seeing — the reference
  // line falls outside the axis and silently disappears, taking the chart's
  // only comparison with it. Round up to a 5% step for legible ticks.
  const controlPercent = metrics.control.recoveryRate * 100
  const highest = Math.max(controlPercent, ...data.map((d) => d.ratePercent), 0)
  const yMax = Math.max(5, Math.ceil((highest * 1.15) / 5) * 5)

  return (
    <section className="card">
      <div className="row-between" style={{ marginBottom: 'var(--space-4)' }}>
        <h2 className="card-title">Recovery rate by failure class (treatment)</h2>
        <span className="muted" style={{ fontSize: 'var(--text-sm)' }}>
          dashed line = control baseline ({formatRate(metrics.control.recoveryRate)})
        </span>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ left: 0, right: 12, top: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
          <XAxis
            dataKey="label"
            tick={axisTick}
            stroke="var(--line-strong)"
            tickLine={false}
            interval={0}
          />
          <YAxis
            domain={[0, yMax]}
            tickFormatter={(v) => `${v}%`}
            tick={axisTick}
            stroke="var(--line-strong)"
            tickLine={false}
            axisLine={false}
            width={44}
          />
          <Tooltip
            content={<ChartTooltip />}
            // The default hover wash is an opaque light grey that hides the
            // bar underneath on the dark palette.
            cursor={{ fill: 'var(--surface-2)', opacity: 0.5 }}
          />
          <ReferenceLine
            y={metrics.control.recoveryRate * 100}
            stroke="var(--control)"
            strokeDasharray="4 4"
            strokeWidth={2}
          />
          <Bar dataKey="ratePercent" fill="var(--accent)" radius={[4, 4, 0, 0]} maxBarSize={72} />
        </BarChart>
      </ResponsiveContainer>
      {emptyReason && (
        <p className="stat-note" style={{ marginTop: 'var(--space-3)' }}>
          {emptyReason}
        </p>
      )}
    </section>
  )
}
