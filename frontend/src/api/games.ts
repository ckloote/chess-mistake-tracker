import { useQuery } from '@tanstack/react-query'
import { apiFetch, toQuery } from './client'

// Mirrors backend/app/schemas/games.GameOut. Kept hand-typed for now —
// switching to generation from /openapi.json is a Phase-12 polish task.
export interface Game {
  id: number
  source: string
  source_game_id: string
  user_color: 'white' | 'black'
  white: string
  black: string
  white_elo: number | null
  black_elo: number | null
  result: string
  time_control: string | null
  played_at: string | null
  has_evals: boolean
  analyzed_at: string | null
  ingested_at: string
}

export interface GameListResponse {
  total: number
  page: number
  page_size: number
  items: Game[]
}

export interface GameFilters {
  source?: string
  from?: string
  to?: string
  result?: string
  color?: 'white' | 'black' | ''
  analyzed_only?: boolean
  has_mistakes?: boolean | null
  page?: number
  page_size?: number
}

export function gamesQueryKey(filters: GameFilters): readonly unknown[] {
  return ['games', filters] as const
}

export function useGamesList(filters: GameFilters) {
  return useQuery({
    queryKey: gamesQueryKey(filters),
    queryFn: ({ signal }) =>
      apiFetch<GameListResponse>(`/games${toQuery({ ...filters })}`, { signal }),
  })
}
