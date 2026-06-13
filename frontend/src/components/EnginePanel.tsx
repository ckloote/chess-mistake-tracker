import { formatScore, type PositionAnalysis } from '../api/analysis'

export interface EnginePanelProps {
  analysis: PositionAnalysis | undefined
  isFetching: boolean
  isError: boolean
  error: unknown
  // Play a UCI move on the explore board (walk into a line).
  onPlayMove: (uci: string) => void
}

// Renders local-Stockfish output for the position currently on the explore
// board: the eval (white-POV) plus the top lines as clickable SAN.
export function EnginePanel({
  analysis,
  isFetching,
  isError,
  error,
  onPlayMove,
}: EnginePanelProps) {
  if (isError) {
    // 503 → stockfish not installed. Anything else is a real error.
    const status =
      error && typeof error === 'object' && 'status' in error
        ? (error as { status?: number }).status
        : undefined
    return (
      <div className="engine-panel">
        <div className="engine-panel-head">Engine</div>
        <p className="muted">
          {status === 503
            ? 'Local Stockfish is unavailable. Install stockfish (or set STOCKFISH_PATH) to explore lines.'
            : `Engine error: ${String(error)}`}
        </p>
      </div>
    )
  }

  const lines = analysis?.lines ?? []
  const top = lines[0]

  return (
    <div className="engine-panel">
      <div className="engine-panel-head">
        <span>Engine</span>
        {top && (
          <span className="engine-eval" title="White's perspective">
            {formatScore(top)}
          </span>
        )}
        {isFetching && <span className="engine-thinking">analyzing…</span>}
      </div>

      {lines.length === 0 && !isFetching && (
        <p className="muted">No engine lines yet.</p>
      )}

      <ol className="engine-lines">
        {lines.map((line, i) => {
          const firstUci = line.pv_uci[0]
          return (
            <li key={i} className="engine-line">
              <span className="engine-line-score">{formatScore(line)}</span>
              <button
                type="button"
                className="engine-line-pv"
                title={firstUci ? `Play ${line.pv_san[0] ?? firstUci}` : undefined}
                disabled={!firstUci}
                onClick={() => firstUci && onPlayMove(firstUci)}
              >
                {line.pv_san.join(' ') || '—'}
              </button>
            </li>
          )
        })}
      </ol>
      {top && (
        <p className="engine-hint muted">
          Click a line to play its first move and see the reply.
        </p>
      )}
    </div>
  )
}
