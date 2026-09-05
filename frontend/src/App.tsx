// Route table.
//
//   /              DashboardPage    funnel + gross vs incremental
//   /cases         CasesPage        filterable list, master-detail shell for the two below
//     (index)      CasesEmptyHint   the docked detail pane's resting state, >=1100px only
//     /cases/:id   CaseDetailPage   the audit timeline — the explainability view
//   /escalations   EscalationsPage  human review queue
//   /demo          DemoPage         seed / simulate / reset
//
// /cases/:id nests under /cases rather than sitting beside it: CasesPage
// renders <Outlet/> for both its own index route and :id, so opening a case
// docks CaseDetailPage beside the list at wide viewports without touching
// the list's filter state or scroll position. Below 1100px CasesPage hides
// its own list pane via CSS the moment a case is selected, so
// CaseDetailPage still reads as a normal full-width page and a direct link
// to /cases/:id still works exactly as before nesting existed.
//
// Dashboard is the landing route on purpose: the first thing on screen is the
// honest number.

import { Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import CaseDetailPage from '@/pages/CaseDetailPage'
import CasesPage, { CasesEmptyHint } from '@/pages/CasesPage'
import DashboardPage from '@/pages/DashboardPage'
import DemoPage from '@/pages/DemoPage'
import EscalationsPage from '@/pages/EscalationsPage'

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/cases" element={<CasesPage />}>
          <Route index element={<CasesEmptyHint />} />
          <Route path=":id" element={<CaseDetailPage />} />
        </Route>
        <Route path="/escalations" element={<EscalationsPage />} />
        <Route path="/demo" element={<DemoPage />} />
      </Routes>
    </AppShell>
  )
}
