import { useParams } from 'react-router-dom'

export function MistakeDetail() {
  const { id } = useParams<{ id: string }>()
  return (
    <div>
      <div className="page-header">
        <div className="page-header-title">
          <span className="eyebrow">Classification</span>
          <h1>Mistake #{id}</h1>
        </div>
      </div>
      <div className="placeholder">
        <span className="placeholder-tag">Forthcoming · Phase 10</span>
        <p>
          The classification surface — Layer A buttons (1–4), Layer B awareness
          (G/D), flag toggles, free-text notes, and a “Save &amp; next” flow
          that walks through unclassified mistakes without lifting a hand from
          the keyboard.
        </p>
      </div>
    </div>
  )
}
