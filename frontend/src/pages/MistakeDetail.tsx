import { useParams } from 'react-router-dom'

export function MistakeDetail() {
  const { id } = useParams<{ id: string }>()
  return (
    <div>
      <div className="page-header">
        <h1>Mistake #{id}</h1>
      </div>
      <p className="muted">
        Coming in Phase 10: classification UI — Layer A buttons, Layer B awareness,
        flag toggles, keyboard shortcuts (1/2/3/4, G/D, Enter, Esc).
      </p>
    </div>
  )
}
