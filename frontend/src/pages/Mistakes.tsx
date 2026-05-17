import { Link } from 'react-router-dom'
import { useUrlState } from '../hooks/useUrlState'
import { useMistakesList, type MistakeFilters } from '../api/mistakes'
import type { Mistake } from '../api/games'

const FILTER_DEFAULTS = {
  // Default-on per IMPLEMENTATION.md — the page exists to keep the queue
  // moving, so unclassified-only is the right opening state.
  unclassified: '1',
  severity: '',
  step: '',
  awareness: '',
  time_pressure: '',
  page: '1',
} as const

type FilterKey = keyof typeof FILTER_DEFAULTS

const PAGE_SIZE = 50

function toApiFilters(urlState: Record<FilterKey, string>): MistakeFilters {
  const page = Number.parseInt(urlState.page, 10)
  const step = Number.parseInt(urlState.step, 10)
  let time_pressure: MistakeFilters['time_pressure'] = ''
  if (urlState.time_pressure === 'true') time_pressure = true
  else if (urlState.time_pressure === 'false') time_pressure = false
  return {
    unclassified_only: urlState.unclassified === '1',
    severity: (urlState.severity as MistakeFilters['severity']) || '',
    step: Number.isFinite(step) && step >= 1 && step <= 4 ? step : undefined,
    awareness: (urlState.awareness as MistakeFilters['awareness']) || '',
    time_pressure,
    page: Number.isFinite(page) && page > 0 ? page : 1,
    page_size: PAGE_SIZE,
  }
}

function severityGlyph(s: Mistake['severity']): string {
  return s === 'blunder' ? '??' : s === 'mistake' ? '?' : '?!'
}

function severityLabel(s: Mistake['severity']): string {
  return s === 'blunder' ? 'Blunder' : s === 'mistake' ? 'Mistake' : 'Inaccuracy'
}

const STEP_LABELS: Record<number, string> = {
  1: 'Missed threat',
  2: 'Missed forcing',
  3: 'Strategic',
  4: 'Blunder check',
}

export function Mistakes() {
  const [filters, setFilters] = useUrlState<FilterKey>(FILTER_DEFAULTS)
  const apiFilters = toApiFilters(filters)
  const query = useMistakesList(apiFilters)

  const total = query.data?.total ?? 0
  const items = query.data?.items ?? []
  const page = apiFilters.page ?? 1
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div>
      <div className="page-header">
        <div className="page-header-title">
          <span className="eyebrow">Queue</span>
          <h1>Mistakes</h1>
        </div>
        <span className="page-header-meta">
          {query.isPending
            ? 'loading…'
            : `${total} ${total === 1 ? 'mistake' : 'mistakes'}`}
        </span>
      </div>

      <div className="filters">
        <div className="filter-group">
          <label htmlFor="f-unclassified">Show</label>
          <select
            id="f-unclassified"
            value={filters.unclassified}
            onChange={(e) =>
              setFilters({ unclassified: e.target.value, page: '1' })
            }
          >
            <option value="1">Unclassified only</option>
            <option value="0">All mistakes</option>
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="f-severity">Severity</label>
          <select
            id="f-severity"
            value={filters.severity}
            onChange={(e) => setFilters({ severity: e.target.value, page: '1' })}
          >
            <option value="">Any</option>
            <option value="blunder">Blunder</option>
            <option value="mistake">Mistake</option>
            <option value="inaccuracy">Inaccuracy</option>
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="f-step">Step</label>
          <select
            id="f-step"
            value={filters.step}
            onChange={(e) => setFilters({ step: e.target.value, page: '1' })}
          >
            <option value="">Any</option>
            <option value="1">1 · Missed threat</option>
            <option value="2">2 · Missed forcing</option>
            <option value="3">3 · Strategic</option>
            <option value="4">4 · Blunder check</option>
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="f-awareness">Awareness</label>
          <select
            id="f-awareness"
            value={filters.awareness}
            onChange={(e) =>
              setFilters({ awareness: e.target.value, page: '1' })
            }
          >
            <option value="">Any</option>
            <option value="got_it_wrong">Got it wrong</option>
            <option value="didnt_see_it">Didn't see it</option>
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="f-tp">Time pressure</label>
          <select
            id="f-tp"
            value={filters.time_pressure}
            onChange={(e) =>
              setFilters({ time_pressure: e.target.value, page: '1' })
            }
          >
            <option value="">Either</option>
            <option value="true">Under pressure</option>
            <option value="false">Not</option>
          </select>
        </div>

        <button
          type="button"
          onClick={() =>
            setFilters({
              unclassified: '1',
              severity: '',
              step: '',
              awareness: '',
              time_pressure: '',
              page: '1',
            })
          }
        >
          Reset
        </button>
      </div>

      {query.isError && (
        <div className="error">
          Failed to load mistakes: {String(query.error)}
        </div>
      )}

      {!query.isError && (
        <div className="games-table-wrap">
          {items.length === 0 && !query.isPending ? (
            <div className="empty">
              <p style={{ margin: 0 }}>The queue is empty.</p>
              <p
                style={{
                  margin: '12px 0 0',
                  fontFamily: 'var(--font-body)',
                  fontStyle: 'normal',
                  fontSize: '0.85rem',
                }}
                className="muted"
              >
                {filters.unclassified === '1'
                  ? 'All matching mistakes are classified. Switch to “All mistakes” to review them.'
                  : 'No mistakes match the current filters.'}
              </p>
            </div>
          ) : (
            <table className="games-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Game</th>
                  <th>Ply</th>
                  <th>Drop</th>
                  <th>Suggested</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <Link
                        to={`/mistakes/${m.id}`}
                        className="mistake-row-severity"
                      >
                        <span
                          className={`severity-mark severity-${m.severity}`}
                        >
                          {severityGlyph(m.severity)}
                        </span>
                        <span className="cell-color" style={{ marginLeft: 4 }}>
                          {severityLabel(m.severity)}
                        </span>
                      </Link>
                    </td>
                    <td className="cell-player">
                      <Link
                        to={`/games/${m.game_id}#ply=${m.ply}`}
                        className="muted"
                        title="Open game review"
                      >
                        #{m.game_id}
                      </Link>
                    </td>
                    <td className="cell-result">{m.ply}</td>
                    <td className="cell-result mistake-drop">
                      −{m.winrate_drop.toFixed(1)}%
                    </td>
                    <td className="cell-source">
                      {m.suggested_step
                        ? `${m.suggested_step} · ${STEP_LABELS[m.suggested_step] ?? ''}`
                        : '—'}
                    </td>
                    <td>
                      {m.classified_at ? (
                        <span className="status-pill analyzed">Classified</span>
                      ) : (
                        <span className="status-pill pending">Pending</span>
                      )}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <Link
                        to={`/mistakes/${m.id}`}
                        className="mistake-row-cta"
                      >
                        Classify →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <div className="pagination">
        <span className="pagination-status">
          Page {page} of {totalPages}
        </span>
        <button
          type="button"
          onClick={() => setFilters({ page: String(page - 1) })}
          disabled={page <= 1}
        >
          Prev
        </button>
        <button
          type="button"
          onClick={() => setFilters({ page: String(page + 1) })}
          disabled={page >= totalPages}
        >
          Next
        </button>
      </div>
    </div>
  )
}
