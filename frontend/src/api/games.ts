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

export interface Position {
  ply: number
  fen: string
  san: string | null
  uci: string | null
  is_user_move: boolean
  eval_cp: number | null
  mate_in: number | null
  clock_ms: number | null
  time_spent_ms: number | null
}

export interface Mistake {
  id: number
  game_id: number
  ply: number
  severity: 'inaccuracy' | 'mistake' | 'blunder'
  eval_before_cp: number | null
  eval_after_cp: number | null
  winrate_before: number
  winrate_after: number
  winrate_drop: number
  best_move_uci: string | null
  best_move_san: string | null
  suggested_step: number | null
  suggestion_confidence: number | null
  suggestion_debug: Record<string, unknown> | null
  classified_step: number | null
  classified_awareness: 'got_it_wrong' | 'didnt_see_it' | null
  time_pressure_flag: boolean
  transition_flag: boolean
  endgame_flag: boolean
  user_notes: string | null
  classified_at: string | null
}

export interface GameDetail extends Game {
  pgn: string
  positions: Position[]
  mistakes: Mistake[]
}

export function useGame(id: number | undefined) {
  return useQuery({
    enabled: id !== undefined && Number.isFinite(id),
    queryKey: ['game', id] as const,
    queryFn: ({ signal }) => apiFetch<GameDetail>(`/games/${id}`, { signal }),
  })
}
