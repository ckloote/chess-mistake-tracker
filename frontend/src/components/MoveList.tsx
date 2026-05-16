import { useEffect, useRef } from 'react'
import type { Position, Mistake } from '../api/games'

interface Props {
  positions: Position[]
  mistakesByPly: Map<number, Mistake>
  activePly: number
  onSelect: (ply: number) => void
}

// Pairs positions[1..] into (white_move, black_move) rows: positions[1] is
// move 1 by white, positions[2] is move 1 by black, etc.
interface PairRow {
  number: number
  white: Position | null
  black: Position | null
}

function buildPairs(positions: Position[]): PairRow[] {
  // Skip ply 0 (starting position, no move).
  const moves = positions.filter((p) => p.ply > 0)
  const rows: PairRow[] = []
  for (let i = 0; i < moves.length; i += 2) {
    const white = moves[i] ?? null
    const black = moves[i + 1] ?? null
    rows.push({
      number: Math.floor(i / 2) + 1,
      white,
      black,
    })
  }
  return rows
}

function severityClass(severity: Mistake['severity']): string {
  return `severity-badge severity-${severity}`
}

function severityChar(severity: Mistake['severity']): string {
  return severity === 'blunder' ? '??' : severity === 'mistake' ? '?' : '?!'
}

export function MoveList({ positions, mistakesByPly, activePly, onSelect }: Props) {
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
        Start
      </button>
      <table>
        <tbody>
          {rows.map((row) => (
            <tr key={row.number}>
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

function MoveCell({ pos, mistake, active, onSelect, activeRef }: MoveCellProps) {
  return (
    <button
      type="button"
      ref={active ? activeRef : undefined}
      className={active ? 'move-cell active' : 'move-cell'}
      onClick={() => onSelect(pos.ply)}
    >
      <span className="move-san">{pos.san ?? '…'}</span>
      {mistake && (
        <span className={severityClass(mistake.severity)} title={mistake.severity}>
          {severityChar(mistake.severity)}
        </span>
      )}
    </button>
  )
}
