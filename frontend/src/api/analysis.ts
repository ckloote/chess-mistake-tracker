import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'

export interface AnalyzedLine {
  // cp / mate are white-POV: positive cp = white is better.
  cp: number | null
  mate: number | null
  pv_uci: string[]
  pv_san: string[]
  depth: number | null
}

export interface PositionAnalysis {
  fen: string
  turn: 'white' | 'black'
  lines: AnalyzedLine[]
}

interface AnalyzePositionBody {
  fen: string
  multipv?: number
  depth?: number
}

// On-demand engine eval for an arbitrary FEN, backed by local Stockfish.
// Keyed by fen+multipv so revisiting a position in the same session is instant.
// Disabled until a fen is present and `enabled` is true (explore mode on).
export function useAnalyzePosition(
  fen: string | null,
  opts: { multipv?: number; depth?: number; enabled?: boolean } = {},
) {
  const { multipv = 3, depth, enabled = true } = opts
  return useQuery({
    enabled: enabled && !!fen,
    // depth belongs in the key: with staleTime Infinity, a shallow cached
    // result must not be served to a request that asked for a deeper search.
    queryKey: ['analysis-position', fen, multipv, depth ?? null] as const,
    // Engine eval of a fixed position at a fixed depth is stable enough to
    // treat as fresh for the session — avoids re-querying on remount.
    staleTime: Infinity,
    queryFn: ({ signal }) => {
      const body: AnalyzePositionBody = { fen: fen as string, multipv }
      if (depth !== undefined) body.depth = depth
      return apiFetch<PositionAnalysis>('/analysis/position', {
        method: 'POST',
        body,
        signal,
      })
    },
  })
}

// Format a white-POV line's score for display. `pov` flips the sign so the
// number reads from one side's perspective when desired.
export function formatScore(
  line: { cp: number | null; mate: number | null },
  pov: 'white' | 'black' = 'white',
): string {
  const sign = pov === 'white' ? 1 : -1
  if (line.mate !== null) {
    return `#${line.mate * sign}` // negative reads "#-3": getting mated in 3
  }
  if (line.cp !== null) {
    const cp = (line.cp * sign) / 100
    const s = cp.toFixed(2)
    return cp > 0 ? `+${s}` : s
  }
  return '–'
}
