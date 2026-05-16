// Thin fetch wrapper. Backend serves at /api/v1; in dev Vite proxies /api to
// :8000, in prod FastAPI will serve the bundle on the same origin. So the
// base path is the same string in both — no env switching needed.

export const API_BASE = '/api/v1'

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

type FetchOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  signal?: AbortSignal
}

export async function apiFetch<T>(path: string, opts: FetchOptions = {}): Promise<T> {
  const { method = 'GET', body, signal } = opts
  const init: RequestInit = {
    method,
    headers: { 'Content-Type': 'application/json' },
    signal,
  }
  if (body !== undefined) {
    init.body = JSON.stringify(body)
  }
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    let detail: unknown = undefined
    try {
      detail = await response.json()
    } catch {
      // ignore — server returned no JSON body
    }
    throw new ApiError(response.status, `HTTP ${response.status}`, detail)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

// Helper to build a query string from a filter record, dropping
// null/undefined/'' values so the URL stays clean.
export function toQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== '',
  )
  if (entries.length === 0) return ''
  const qs = new URLSearchParams()
  for (const [k, v] of entries) qs.set(k, String(v))
  return `?${qs.toString()}`
}
