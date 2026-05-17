import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, toQuery } from './client'
import type { Game, Mistake, Position } from './games'

export interface MistakeListResponse {
  total: number
  page: number
  page_size: number
  items: Mistake[]
}

export interface MistakeDetail extends Mistake {
  game: Game
  position_before: Position | null
  position_at_move: Position | null
  position_after_response: Position | null
}

export interface MistakeFilters {
  game_id?: number
  step?: number
  awareness?: 'got_it_wrong' | 'didnt_see_it' | ''
  severity?: 'inaccuracy' | 'mistake' | 'blunder' | ''
  time_pressure?: boolean | ''
  unclassified_only?: boolean
  from?: string
  to?: string
  page?: number
  page_size?: number
}

export function mistakesQueryKey(filters: MistakeFilters): readonly unknown[] {
  return ['mistakes', filters] as const
}

export function useMistakesList(filters: MistakeFilters) {
  return useQuery({
    queryKey: mistakesQueryKey(filters),
    queryFn: ({ signal }) =>
      apiFetch<MistakeListResponse>(`/mistakes${toQuery({ ...filters })}`, {
        signal,
      }),
  })
}

export function useMistake(id: number | undefined) {
  return useQuery({
    enabled: id !== undefined && Number.isFinite(id),
    queryKey: ['mistake', id] as const,
    queryFn: ({ signal }) =>
      apiFetch<MistakeDetail>(`/mistakes/${id}`, { signal }),
  })
}

export interface MistakeUpdatePayload {
  classified_step?: number | null
  classified_awareness?: 'got_it_wrong' | 'didnt_see_it' | null
  user_notes?: string | null
  time_pressure_flag?: boolean
  transition_flag?: boolean
  endgame_flag?: boolean
}

export function useUpdateMistake() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number
      payload: MistakeUpdatePayload
    }) =>
      apiFetch<Mistake>(`/mistakes/${id}`, {
        method: 'PATCH',
        body: payload,
      }),
    onSuccess: (data) => {
      // Invalidate the individual detail and any list that may include it —
      // unclassified queues will rebuild without this mistake on next fetch.
      qc.invalidateQueries({ queryKey: ['mistake', data.id] })
      qc.invalidateQueries({ queryKey: ['mistakes'] })
    },
  })
}
