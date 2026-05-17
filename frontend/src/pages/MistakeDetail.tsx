import { useMemo } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import type { Key } from 'chessground/types'
import { Chessground, type BoardArrow } from '../components/Chessground'
import { ClassificationForm } from '../components/ClassificationForm'
import {
  useMistake,
  useMistakesList,
  useUpdateMistake,
  type MistakeUpdatePayload,
} from '../api/mistakes'
import type { Mistake } from '../api/games'

const STEP_LABELS: Record<number, string> = {
  1: 'Missed opponent threat',
  2: 'Missed forcing move',
  3: 'Strategic inaccuracy',
  4: 'Failed blunder check',
}

function parseUci(uci: string): { from: Key; to: Key } | null {
  if (uci.length < 4) return null
  return { from: uci.slice(0, 2) as Key, to: uci.slice(2, 4) as Key }
}

function extractBestUci(m: Mistake): string | null {
  if (m.best_move_uci) return m.best_move_uci
  const debug = m.suggestion_debug
  if (debug && typeof debug === 'object' && 'm_best_uci' in debug) {
    const v = (debug as { m_best_uci?: unknown }).m_best_uci
    if (typeof v === 'string') return v
  }
  return null
}

function severityGlyph(s: Mistake['severity']): string {
  return s === 'blunder' ? '??' : s === 'mistake' ? '?' : '?!'
}

function severityLabel(s: Mistake['severity']): string {
  return s === 'blunder' ? 'Blunder' : s === 'mistake' ? 'Mistake' : 'Inaccuracy'
}

export function MistakeDetail() {
  const { id } = useParams<{ id: string }>()
  const mistakeId = id ? Number.parseInt(id, 10) : undefined
  const navigate = useNavigate()

  const detailQuery = useMistake(mistakeId)
  // The unclassified queue powers the save-and-next flow. Page size is
  // generous so a typical session doesn't have to paginate mid-classification.
  const queueQuery = useMistakesList({
    unclassified_only: true,
    page: 1,
    page_size: 200,
  })

  const update = useUpdateMistake()

  const queue = queueQuery.data?.items ?? []
  const queueIndex = useMemo(
    () => (mistakeId ? queue.findIndex((m) => m.id === mistakeId) : -1),
    [queue, mistakeId],
  )

  function navigateToNextUnclassified() {
    if (queue.length === 0) {
      navigate('/mistakes')
      return
    }
    if (queueIndex === -1) {
      // Current mistake is no longer in the unclassified queue (just got
      // classified, or filters changed). Jump to the head of the queue.
      const head = queue[0]
      if (head) navigate(`/mistakes/${head.id}`)
      else navigate('/mistakes')
      return
    }
    const next = queue[queueIndex + 1]
    if (next) {
      navigate(`/mistakes/${next.id}`)
    } else {
      // End of queue — back to the list (which will show "queue empty" if
      // everything's classified).
      navigate('/mistakes')
    }
  }

  if (detailQuery.isPending) {
    return (
      <div>
        <div className="page-header">
          <div className="page-header-title">
            <span className="eyebrow">Classification</span>
            <h1>Mistake #{id}</h1>
          </div>
        </div>
        <p className="muted">Loading…</p>
      </div>
    )
  }
  if (detailQuery.isError || !detailQuery.data) {
    return (
      <div>
        <div className="page-header">
          <div className="page-header-title">
            <span className="eyebrow">Classification</span>
            <h1>Mistake #{id}</h1>
          </div>
        </div>
        <div className="error">
          Failed to load mistake: {String(detailQuery.error)}
        </div>
      </div>
    )
  }

  const detail = detailQuery.data
  const game = detail.game

  // The classification board shows the position BEFORE the user's move,
  // overlaid with both candidate moves.
  const boardFen = detail.position_before?.fen ?? detail.position_at_move?.fen
  const userMove = detail.position_at_move?.uci
    ? parseUci(detail.position_at_move.uci)
    : null
  const bestUci = extractBestUci(detail)
  const best = bestUci ? parseUci(bestUci) : null

  const arrows: BoardArrow[] = []
  if (userMove) {
    arrows.push({ orig: userMove.from, dest: userMove.to, brush: 'red' })
  }
  if (best) {
    arrows.push({ orig: best.from, dest: best.to, brush: 'green' })
  }

  function handleSave(payload: MistakeUpdatePayload) {
    if (mistakeId === undefined) return
    update.mutate(
      { id: mistakeId, payload },
      {
        onSuccess: () => {
          // After a successful save the queue invalidates and refetches.
          // Use the cached index to advance — the freshly-classified mistake
          // is at the current position, so the NEXT in the old queue is the
          // right next id. (Even if the new queue removes us, queueIndex
          // points at "where we were" in the old queue.)
          navigateToNextUnclassified()
        },
      },
    )
  }

  const queuePosition =
    queueIndex >= 0
      ? `${queueIndex + 1} of ${queue.length} unclassified`
      : queue.length > 0
        ? `${queue.length} unclassified`
        : 'queue empty'

  return (
    <div>
      <div className="page-header">
        <div className="page-header-title">
          <span className="eyebrow">Classification</span>
          <h1 className="review-title">
            <span className={`severity-mark severity-${detail.severity}`}>
              {severityGlyph(detail.severity)}
            </span>
            <span>{severityLabel(detail.severity)}</span>
            <span className="vs">at ply {detail.ply}</span>
            <span className="result">−{detail.winrate_drop.toFixed(1)}%</span>
          </h1>
        </div>
        <div className="classify-back-group">
          <span className="page-header-meta">{queuePosition}</span>
          <Link to="/mistakes" className="review-back">
            ← Queue
          </Link>
        </div>
      </div>

      <div className="classify-context">
        <span className="eyebrow">From</span>
        <Link
          to={`/games/${game.id}`}
          className="classify-context-game"
        >
          {game.white} <span className="vs">vs</span> {game.black}{' '}
          <span className="result">{game.result.replace(/-/g, '–')}</span>
        </Link>
        {detail.suggested_step && (
          <span className="classify-context-suggestion">
            Heuristic suggests Step {detail.suggested_step} ·{' '}
            {STEP_LABELS[detail.suggested_step]}
            {detail.suggestion_confidence !== null
              ? ` (confidence ${(detail.suggestion_confidence * 100).toFixed(0)}%)`
              : ''}
          </span>
        )}
      </div>

      <div className="review-layout">
        <div className="review-board">
          <Chessground
            fen={boardFen ?? ''}
            orientation={game.user_color}
            arrows={arrows}
          />
          <div className="board-meta">
            <span>
              <span className="ply-marker">{detail.ply - 1}</span>
              <span className="faint"> · your move</span>
              {detail.position_at_move?.san ? (
                <>
                  {' '}
                  <span className="severity-mark severity-blunder">
                    ←
                  </span>{' '}
                  <span className="ply-san">{detail.position_at_move.san}</span>
                </>
              ) : null}
            </span>
            {best && (
              <span>
                <span className="severity-mark severity-inaccuracy">→</span>{' '}
                <span style={{ color: 'var(--ink-forest)', fontWeight: 600 }}>
                  {detail.best_move_san ?? bestUci}
                </span>
              </span>
            )}
          </div>
          {update.isError && (
            <div className="error" style={{ marginTop: 12 }}>
              Save failed: {String(update.error)}
            </div>
          )}
        </div>

        <aside className="review-side">
          <ClassificationForm
            mistake={detail}
            saving={update.isPending}
            onSave={handleSave}
            onSkip={navigateToNextUnclassified}
            onBack={() => navigate('/mistakes')}
          />
        </aside>
      </div>
    </div>
  )
}
