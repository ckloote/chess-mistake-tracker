import { useState } from 'react'
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

export function MistakeDetailPanel({ mistake, total, index, onPrev, onNext }: Props) {
  const [showDebug, setShowDebug] = useState(false)
  const stepLabel = mistake.suggested_step
    ? `Step ${mistake.suggested_step} · ${STEP_LABELS[mistake.suggested_step] ?? ''}`
    : '—'

  return (
    <section className="mistake-panel">
      <header className="mistake-panel-header">
        <div>
          <span className={severityClass(mistake.severity)}>
            {severityLabel(mistake.severity)}
          </span>
          <span className="muted" style={{ marginLeft: 8 }}>
            ply {mistake.ply}
          </span>
        </div>
        <div className="mistake-nav">
          <span className="muted">
            {index + 1} / {total}
          </span>
          <button type="button" onClick={onPrev} disabled={total <= 1}>
            Prev
          </button>
          <button type="button" onClick={onNext} disabled={total <= 1}>
            Next
          </button>
        </div>
      </header>

      <dl className="mistake-stats">
        <div>
          <dt>Win% before</dt>
          <dd>{formatWinrate(mistake.winrate_before)}</dd>
        </div>
        <div>
          <dt>Win% after</dt>
          <dd>{formatWinrate(mistake.winrate_after)}</dd>
        </div>
        <div>
          <dt>Drop</dt>
          <dd>−{formatWinrate(mistake.winrate_drop)}</dd>
        </div>
        <div>
          <dt>Suggested</dt>
          <dd>{stepLabel}</dd>
        </div>
        {mistake.suggestion_confidence !== null && (
          <div>
            <dt>Confidence</dt>
            <dd>{(mistake.suggestion_confidence * 100).toFixed(0)}%</dd>
          </div>
        )}
        {mistake.best_move_san && (
          <div>
            <dt>Engine best</dt>
            <dd>{mistake.best_move_san}</dd>
          </div>
        )}
      </dl>

      <div className="mistake-flags">
        {mistake.time_pressure_flag && <span className="chip">time pressure</span>}
        {mistake.transition_flag && <span className="chip">transition</span>}
        {mistake.endgame_flag && <span className="chip">endgame</span>}
      </div>

      {mistake.suggestion_debug && (
        <details
          className="mistake-debug"
          open={showDebug}
          onToggle={(e) => setShowDebug((e.target as HTMLDetailsElement).open)}
        >
          <summary>suggestion_debug</summary>
          <pre>{JSON.stringify(mistake.suggestion_debug, null, 2)}</pre>
        </details>
      )}
    </section>
  )
}
