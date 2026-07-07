import { useEffect, useRef } from 'react'
import type { Position, Mistake } from '../api/games'

interface Props {
  positions: Position[]
  mistakesByPly: Map<number, Mistake>
  activePly: number
  onSelect: (ply: number) => void
}

// Pairs positions[1..] into (white_move, black_move) score-sheet rows.
interface PairRow {
  number: number
  white: Position | null
  black: Position | null
}

// Who played the move that produced this position: the opposite of the FEN's
// side-to-move. Derived from the FEN, not ply parity, because study chapters
// can start from a custom [FEN] with black to move (mirrors the backend's
// mover_color in services/analysis.py).
function moverOf(p: Position): 'white' | 'black' {
  return p.fen.split(' ')[1] === 'w' ? 'black' : 'white'
}

// Move number for the move that produced this position. The FEN's fullmove
// counter increments after black's move, so a black move's number is one less
// than its resulting FEN reports.
function moveNumberOf(p: Position): number {
  const full = Number.parseInt(p.fen.split(' ')[5] ?? '1', 10) || 1
  return moverOf(p) === 'white' ? full : full - 1
}

function buildPairs(positions: Position[]): PairRow[] {
  // Skip ply 0 (starting position, no move).
  const moves = positions.filter((p) => p.ply > 0)
  const rows: PairRow[] = []
  for (const p of moves) {
    const number = moveNumberOf(p)
    const last = rows[rows.length - 1]
    if (moverOf(p) === 'white') {
      rows.push({ number, white: p, black: null })
    } else if (last && last.number === number && last.black === null) {
      last.black = p
    } else {
      // Black move with no white half to pair with — a black-first start.
      rows.push({ number, white: null, black: p })
    }
  }
  return rows
}

function severityClass(severity: Mistake['severity']): string {
  return `severity-mark severity-${severity}`
}

// Classical chess-book annotation glyphs.
function severityGlyph(severity: Mistake['severity']): string {
  return severity === 'blunder' ? '??' : severity === 'mistake' ? '?' : '?!'
}

export function MoveList({
  positions,
  mistakesByPly,
  activePly,
  onSelect,
}: Props) {
  const rows = buildPairs(positions)
  const activeRef = useRef<HTMLButtonElement>(null)

  // Keep the active move visible without taking focus from the page.
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest', behavior: 'auto' })
  }, [activePly])

  return (
    <div className="move-list">
      <button
        type="button"
        className={activePly === 0 ? 'move-start active' : 'move-start'}
        onClick={() => onSelect(0)}
      >
        Initial position
      </button>
      <table>
        <tbody>
          {rows.map((row) => (
            <tr key={row.white?.ply ?? row.black?.ply ?? row.number}>
              <td className="move-num">{row.number}.</td>
              <td>
                {row.white && (
                  <MoveCell
                    pos={row.white}
                    mistake={mistakesByPly.get(row.white.ply)}
                    active={activePly === row.white.ply}
                    onSelect={onSelect}
                    activeRef={activeRef}
                  />
                )}
              </td>
              <td>
                {row.black && (
                  <MoveCell
                    pos={row.black}
                    mistake={mistakesByPly.get(row.black.ply)}
                    active={activePly === row.black.ply}
                    onSelect={onSelect}
                    activeRef={activeRef}
                  />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

interface MoveCellProps {
  pos: Position
  mistake: Mistake | undefined
  active: boolean
  onSelect: (ply: number) => void
  activeRef: React.RefObject<HTMLButtonElement | null>
}

function MoveCell({
  pos,
  mistake,
  active,
  onSelect,
  activeRef,
}: MoveCellProps) {
  return (
    <button
      type="button"
      ref={active ? activeRef : undefined}
      className={active ? 'move-cell active' : 'move-cell'}
      onClick={() => onSelect(pos.ply)}
    >
      <span className="move-san">{pos.san ?? '…'}</span>
      {mistake && (
        <span
          className={severityClass(mistake.severity)}
          title={mistake.severity}
        >
          {severityGlyph(mistake.severity)}
        </span>
      )}
    </button>
  )
}
