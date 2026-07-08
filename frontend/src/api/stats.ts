import { useQuery } from '@tanstack/react-query'
import { apiFetch, toQuery } from './client'

export interface StepCount {
  step: number
  count: number
}
export interface AwarenessCount {
  awareness: string
  count: number
}
export interface SeverityCount {
  severity: string
  count: number
}

export interface StatsSummary {
  total_games: number
  total_mistakes: number
  classified: number
  unclassified: number
  by_suggested_step: StepCount[]
  by_classified_step: StepCount[]
  by_awareness: AwarenessCount[]
  by_severity: SeverityCount[]
}

export interface PrescriptionItem {
  step: number
  awareness: string
  count: number
  share: number // of classified mistakes (0..1)
  suggestion: string
}
export interface Prescription {
  classified_mistakes: number
  items: PrescriptionItem[]
}

export interface BreakdownItem {
  label: string
  count: number
}
export interface Breakdown {
  by: string
  items: BreakdownItem[]
}

// Shared filters accepted by every /stats/* endpoint (F4). Dates are
// YYYY-MM-DD strings; omitted/empty fields mean "no filter" (toQuery drops
// them). Objects hash stably in TanStack Query keys, so passing the record
// straight into queryKey gives correct per-slice caching.
export interface StatsFilters {
  from?: string
  to?: string
  source?: string
  color?: string
  severity?: string
  speed?: string
}

const NO_FILTERS: StatsFilters = {}

export function useSummary(filters: StatsFilters = NO_FILTERS) {
  return useQuery({
    queryKey: ['stats', 'summary', filters] as const,
    queryFn: ({ signal }) =>
      apiFetch<StatsSummary>(`/stats/summary${toQuery({ ...filters })}`, {
        signal,
      }),
  })
}

export function usePrescription(top = 3, filters: StatsFilters = NO_FILTERS) {
  return useQuery({
    queryKey: ['stats', 'prescription', top, filters] as const,
    queryFn: ({ signal }) =>
      apiFetch<Prescription>(
        `/stats/training-prescription${toQuery({ top, ...filters })}`,
        { signal },
      ),
  })
}

export function useBreakdown(by: string, filters: StatsFilters = NO_FILTERS) {
  return useQuery({
    queryKey: ['stats', 'breakdown', by, filters] as const,
    queryFn: ({ signal }) =>
      apiFetch<Breakdown>(`/stats/breakdown${toQuery({ by, ...filters })}`, {
        signal,
      }),
  })
}

// Shared label/colour maps so Dashboard and Stats read consistently.
export const STEP_LABELS: Record<number, string> = {
  1: 'Missed opponent threat',
  2: 'Missed forcing move',
  3: 'Strategic inaccuracy',
  4: 'Failed blunder check',
}

export const AWARENESS_LABELS: Record<string, string> = {
  didnt_see_it: "Didn't see it",
  got_it_wrong: 'Got it wrong',
}

// Classical annotation palette (mirrors the CSS tokens).
export const SEVERITY_COLOR: Record<string, string> = {
  blunder: '#7a1a1f', // --ink-port
  mistake: '#b1571e', // --ink-rust
  inaccuracy: '#a88513', // --ink-mustard
}
export const SEVERITY_GLYPH: Record<string, string> = {
  blunder: '??',
  mistake: '?',
  inaccuracy: '?!',
}
export const SEVERITY_ORDER = ['blunder', 'mistake', 'inaccuracy'] as const
