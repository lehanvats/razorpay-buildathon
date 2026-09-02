// Route table.
//
//   /              DashboardPage    funnel + gross vs incremental
//   /cases         CasesPage        filterable list
//   /cases/:id     CaseDetailPage   the audit timeline — the explainability view
//   /escalations   EscalationsPage  human review queue
//   /demo          DemoPage         seed / simulate / reset
//
// Dashboard is the landing route on purpose: the first thing on screen is the
// honest number.

import { Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import CaseDetailPage from '@/pages/CaseDetailPage'
import CasesPage from '@/pages/CasesPage'
import DashboardPage from '@/pages/DashboardPage'
import DemoPage from '@/pages/DemoPage'
import EscalationsPage from '@/pages/EscalationsPage'

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/cases" element={<CasesPage />} />
        <Route path="/cases/:id" element={<CaseDetailPage />} />
        <Route path="/escalations" element={<EscalationsPage />} />
        <Route path="/demo" element={<DemoPage />} />
      </Routes>
    </AppShell>
  )
}
