import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Mistake } from '../api/games'

interface Props {
  mistake: Mistake
  total: number
  index: number
  onPrev: () => void
  onNext: () => void
}

const STEP_LABELS: Record<number, string> = {
  1: 'Missed opponent threat',
  2: 'Missed forcing move',
  3: 'Strategic inaccuracy',
  4: 'Failed blunder check',
}

function severityLabel(s: Mistake['severity']): string {
  return s === 'blunder' ? 'Blunder' : s === 'mistake' ? 'Mistake' : 'Inaccuracy'
}

function severityClass(s: Mistake['severity']): string {
  return `severity-badge severity-${s}`
}

function formatWinrate(w: number): string {
  return `${w.toFixed(1)}%`
}

export function MistakeDetailPanel({
  mistake,
  total,
  index,
  onPrev,
  onNext,
}: Props) {
  const [showDebug, setShowDebug] = useState(false)

  return (
    <section className="mistake-panel">
      <header className="mistake-panel-eyebrow">
        <span className={severityClass(mistake.severity)}>
          {severityLabel(mistake.severity)}
        </span>
        <span className="mistake-panel-eyebrow-meta">ply {mistake.ply}</span>
      </header>

      {mistake.suggested_step && (
        <div className="mistake-headline">
          <span className="mistake-headline-step">
            <span className="step-num">{mistake.suggested_step}.</span>
            {STEP_LABELS[mistake.suggested_step] ?? '—'}
          </span>
          {mistake.suggestion_confidence !== null && (
            <span className="mistake-headline-conf">
              confidence {(mistake.suggestion_confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
      )}

      <dl className="mistake-stats">
        <div>
          <dt>Win% before</dt>
          <dd className="numeric">{formatWinrate(mistake.winrate_before)}</dd>
        </div>
        <div>
          <dt>Win% after</dt>
          <dd className="numeric">{formatWinrate(mistake.winrate_after)}</dd>
        </div>
        <div>
          <dt>Drop</dt>
          <dd className="numeric drop">−{formatWinrate(mistake.winrate_drop)}</dd>
        </div>
        {mistake.best_move_san && (
          <div>
            <dt>Engine best</dt>
            <dd className="best-move">{mistake.best_move_san}</dd>
          </div>
        )}
      </dl>

      {(mistake.time_pressure_flag ||
        mistake.transition_flag ||
        mistake.endgame_flag) && (
        <div className="mistake-flags">
          {mistake.time_pressure_flag && (
            <span className="chip">Time pressure</span>
          )}
          {mistake.transition_flag && <span className="chip">Transition</span>}
          {mistake.endgame_flag && <span className="chip">Endgame</span>}
        </div>
      )}

      <div className="mistake-panel-actions">
        <Link
          to={`/mistakes/${mistake.id}`}
          className="mistake-classify-cta"
        >
          {mistake.classified_at ? 'Edit classification' : 'Classify'}
          <span aria-hidden="true"> →</span>
        </Link>
        <div className="mistake-nav">
          <span className="mistake-nav-counter">
            {index + 1} of {total}
          </span>
          <button type="button" onClick={onPrev} disabled={total <= 1}>
            Prev
          </button>
          <button type="button" onClick={onNext} disabled={total <= 1}>
            Next
          </button>
        </div>
      </div>

      {mistake.suggestion_debug && (
        <details
          className="mistake-debug"
          open={showDebug}
          onToggle={(e) =>
            setShowDebug((e.target as HTMLDetailsElement).open)
          }
        >
          <summary>Suggestion debug</summary>
          <pre>{JSON.stringify(mistake.suggestion_debug, null, 2)}</pre>
        </details>
      )}
    </section>
  )
}
