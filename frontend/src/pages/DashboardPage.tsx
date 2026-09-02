// Landing route. Layout order is the argument:
//
//   1. RecoveryCounters   gross vs incremental, equal weight
//   2. FunnelChart        failed -> eligible -> treated -> recovered
//   3. ClassBreakdown     per-class, treatment vs control      \ paired,
//      + ControlGroupPanel the holdout, explained, its caveat  / see below
//
// The first two stay full-width, single cards in reading order — they are
// each one self-contained story (the headline number, the flow) that a
// side-by-side layout would only compress. ClassBreakdown and
// ControlGroupPanel are different: the chart's dashed reference line IS the
// control rate, so the panel that explains where that line comes from
// belongs beside it, not two full-width cards further down the page.
//
// Polls while a demo batch is running so counters climb on camera (the 1:30
// beat of the video).

import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { ErrorNote, Loading } from '@/components/PageState'
import { ClassBreakdown } from '@/components/dashboard/ClassBreakdown'
import { ControlGroupPanel } from '@/components/dashboard/ControlGroupPanel'
import { FunnelChart } from '@/components/dashboard/FunnelChart'
import { RecoveryCounters } from '@/components/dashboard/RecoveryCounters'

export default function DashboardPage() {
  const { data: metrics, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: api.getDashboard,
    refetchInterval: 4_000,
  })

  if (isLoading) return <Loading what="the dashboard" />
  if (error || !metrics) return <ErrorNote>Could not load the dashboard.</ErrorNote>

  return (
    <div className="stack">
      <header className="page-head">
        <h1 className="page-title">Recovery</h1>
        <p className="page-sub">
          Gross is what every vendor in this market reports. Incremental is what a live 20%
          holdout says we actually caused. Both are on screen, at the same size.
        </p>
      </header>

      <RecoveryCounters metrics={metrics} />
      <FunnelChart funnel={metrics.funnel} />
      <div className="dashboard-split">
        <ClassBreakdown metrics={metrics} />
        <ControlGroupPanel metrics={metrics} />
      </div>
    </div>
  )
}
