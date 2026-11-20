export interface Check {
  id: number
  monitor_id: number
  scheduled_at: string
  started_at: string
  finished_at: string
  elapsed_ms: number
  success: boolean
  http_status: number | null
  failure_reason: string | null
  gap_before: boolean
}

export interface Incident {
  id: number
  first_failure_at: string
  confirmed_at: string
  resolved_at: string | null
}

export interface Monitor {
  id: number
  name: string
  url: string
  interval_seconds: number
  expected_status: number
  timeout_seconds: number
  enabled: boolean
  created_at: string
  next_run_at: string | null
  latest_check: Check | null
  open_incident: Incident | null
  awaiting_recovery: boolean
  overdue: boolean
}

export interface Event {
  id: number
  incident_id: number
  monitor_id: number
  monitor_name: string
  event_type: 'outage' | 'recovery'
  created_at: string
  message: string
}

export interface Point {
  started_at: string
  response_ms: number | null
  success: boolean
  gap_before: boolean
}

export interface Metrics {
  total_checks: number
  successful_checks: number
  availability_percent: number | null
  response_samples: number
  mean_ms: number | null
  p95_ms: number | null
  points: Point[]
}

export interface CheckPage {
  items: Check[]
  page: number
  page_size: number
  has_more: boolean
}

export type DemoEndpoint = 'primary' | 'secondary'
export type DemoBehavior = { mode: 'healthy' | 'unavailable' | 'delayed'; delay_ms: number }

type RequestError = { loc: string[]; msg: string }

export class ApiError extends Error {
  constructor(message: string, public status: number, public fields: Record<string, string> = {}) {
    super(message)
  }
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options)
  if (response.ok) return response.json()

  const body = await response.json().catch(() => ({}))
  const detail = body.detail
  const fields = Array.isArray(detail)
    ? Object.fromEntries(detail.map(({ loc, msg }: RequestError) =>
        [loc.at(-1), msg.replace(/^Value error, /, '')]))
    : {}
  const message = typeof detail === 'string' ? detail : `Request failed (HTTP ${response.status}).`
  throw new ApiError(message, response.status, fields)
}

export function send<T>(path: string, method: 'POST' | 'PATCH' | 'PUT', payload: object) {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export const MONITORS = '/api/monitors'
export const DEMO_CONTROL = '/demo/control'
