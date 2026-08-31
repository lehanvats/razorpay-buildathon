// Thin fetch wrapper over the FastAPI backend.
//
// The dev server proxies /api to localhost:8000 (see vite.config.ts), so the
// default base URL is a relative path and the browser never makes a
// cross-origin request.

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // TODO(step-08): fetch, throw on non-2xx with the FastAPI error detail
  // surfaced, parse JSON.
  throw new Error('not implemented')
}

export const api = {
  // Dashboard is fetched as one payload so the gross and incremental
  // counters can never disagree by being read at different moments.
  getDashboard: () => request('/dashboard'),

  listCases: (params?: { arm?: string; status?: string }) => request('/cases'),
  getCase: (id: string) => request(`/cases/${id}`),

  listEscalations: () => request('/escalations'),
  resolveEscalation: (id: string, note: string) =>
    request(`/escalations/${id}/resolve`, { method: 'POST' }),

  // Demo controls — 404 when the backend has demo_mode off.
  seed: (count: number) => request('/demo/seed', { method: 'POST' }),
  simulate: () => request('/demo/simulate', { method: 'POST' }),
  reset: () => request('/demo/reset', { method: 'POST' }),
}
