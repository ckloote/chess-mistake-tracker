import { useParams } from 'react-router-dom'

export function GameDetail() {
  const { id } = useParams<{ id: string }>()
  return (
    <div>
      <div className="page-header">
        <h1>Game #{id}</h1>
      </div>
      <p className="muted">
        Coming in Phase 9: chessground board, move list with mistakes highlighted,
        per-mistake detail panel.
      </p>
    </div>
  )
}
