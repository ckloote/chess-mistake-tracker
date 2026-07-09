import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from './client'

// Mirrors backend/app/schemas/settings.SettingsOut.
export interface AppSettings {
  lichess_username: string // read-only; changing it means re-seeding
  stockfish_available: boolean // read-only capability flag from the host
  chesscom_username: string | null // editable; drives the chess.com import
  winrate_inaccuracy: number
  winrate_mistake: number
  winrate_blunder: number
  suppress_below: number
  suppress_above_before: number
  suppress_above_after: number
  lichess_study_ids: string[]
  study_player_aliases: string[]
}

// PATCH body — all optional; the read-only fields are not editable.
export type SettingsUpdate = Partial<
  Omit<AppSettings, 'lichess_username' | 'stockfish_available'>
>

// The fields whose change makes existing Mistake rows stale — used to decide
// when to show the "re-analyze to apply" warning after a save.
export const DETECTION_FIELDS = [
  'winrate_inaccuracy',
  'winrate_mistake',
  'winrate_blunder',
  'suppress_below',
  'suppress_above_before',
  'suppress_above_after',
] as const satisfies readonly (keyof AppSettings)[]

export function useSettings() {
  return useQuery({
    queryKey: ['settings'] as const,
    queryFn: ({ signal }) => apiFetch<AppSettings>('/settings', { signal }),
  })
}

export function useUpdateSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: SettingsUpdate) =>
      apiFetch<AppSettings>('/settings', { method: 'PATCH', body: payload }),
    onSuccess: (data) => {
      qc.setQueryData(['settings'], data)
    },
  })
}
