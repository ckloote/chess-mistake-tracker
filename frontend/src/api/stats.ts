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

export function useSummary() {
  return useQuery({
    queryKey: ['stats', 'summary'] as const,
    queryFn: ({ signal }) => apiFetch<StatsSummary>('/stats/summary', { signal }),
  })
}

export function usePrescription(top = 3) {
  return useQuery({
    queryKey: ['stats', 'prescription', top] as const,
    queryFn: ({ signal }) =>
      apiFetch<Prescription>(
        `/stats/training-prescription${toQuery({ top })}`,
        { signal },
      ),
  })
}

export function useBreakdown(by: string) {
  return useQuery({
    queryKey: ['stats', 'breakdown', by] as const,
    queryFn: ({ signal }) =>
      apiFetch<Breakdown>(`/stats/breakdown${toQuery({ by })}`, { signal }),
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
