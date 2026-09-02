// Thin fetch wrapper over the FastAPI backend.
//
// The dev server proxies /api to localhost:8000 (see vite.config.ts), so the
// default base URL is a relative path and the browser never makes a
// cross-origin request.

import type {
  CaseDetail,
  CaseSummary,
  DashboardMetrics,
  EscalationItem,
  SeedResult,
  SimulateResult,
} from './types'

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `request failed with ${status}`)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    // FastAPI's HTTPException body is {"detail": ...}; fall back to the raw
    // text for anything else (a 404 with no body, a proxy error page).
    let detail: unknown
    try {
      detail = (await res.json()).detail
    } catch {
      detail = await res.text().catch(() => undefined)
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

function query(params?: Record<string, string | undefined>): string {
  if (!params) return ''
  const entries = Object.entries(params).filter(([, v]) => v !== undefined) as [string, string][]
  if (entries.length === 0) return ''
  return `?${new URLSearchParams(entries).toString()}`
}

export const api = {
  // Dashboard is fetched as one payload so the gross and incremental
  // counters can never disagree by being read at different moments.
  getDashboard: () => request<DashboardMetrics>('/dashboard'),

  listCases: (params?: { arm?: string; status?: string; failureClass?: string }) =>
    request<CaseSummary[]>(
      `/cases${query({ arm: params?.arm, status: params?.status, failure_class: params?.failureClass })}`,
    ),
  getCase: (id: string) => request<CaseDetail>(`/cases/${id}`),

  listEscalations: () => request<EscalationItem[]>('/escalations'),
  resolveEscalation: (id: string, note: string) =>
    request<{ status: string; caseId: string }>(`/escalations/${id}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    }),

  // Demo controls — 404 when the backend has demo_mode off.
  seed: (count: number, seed?: number) =>
    request<SeedResult>('/demo/seed', { method: 'POST', body: JSON.stringify({ count, seed }) }),
  simulate: () => request<SimulateResult>('/demo/simulate', { method: 'POST' }),
  reset: () => request<{ status: string }>('/demo/reset', { method: 'POST' }),
}

export { ApiError }
