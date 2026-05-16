import { Link } from 'react-router-dom'
import { useUrlState } from '../hooks/useUrlState'
import { useGamesList, type GameFilters } from '../api/games'

const FILTER_DEFAULTS = {
  source: '',
  color: '',
  result: '',
  from: '',
  to: '',
  page: '1',
} as const

type FilterKey = keyof typeof FILTER_DEFAULTS

const PAGE_SIZE = 25

// Translate URL strings into the typed filter object the hook expects.
function toApiFilters(urlState: Record<FilterKey, string>): GameFilters {
  const page = Number.parseInt(urlState.page, 10)
  return {
    source: urlState.source || undefined,
    color: (urlState.color as GameFilters['color']) || undefined,
    result: urlState.result || undefined,
    from: urlState.from || undefined,
    to: urlState.to || undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
    page_size: PAGE_SIZE,
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toISOString().slice(0, 10)
}

function statusLabel(g: { has_evals: boolean; analyzed_at: string | null }): string {
  if (g.analyzed_at) return 'analyzed'
  if (g.has_evals) return 'pending'
  return 'needs Lichess analysis'
}

export function Games() {
  const [filters, setFilters] = useUrlState<FilterKey>(FILTER_DEFAULTS)
  const apiFilters = toApiFilters(filters)
  const query = useGamesList(apiFilters)

  const total = query.data?.total ?? 0
  const items = query.data?.items ?? []
  const page = apiFilters.page ?? 1
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div>
      <div className="page-header">
        <h1>Games</h1>
        <span className="muted">
          {query.isPending ? 'loading…' : `${total} total`}
        </span>
      </div>

      <div className="filters">
        <div className="filter-group">
          <label htmlFor="f-source">Source</label>
          <select
            id="f-source"
            value={filters.source}
            onChange={(e) => setFilters({ source: e.target.value, page: '1' })}
          >
            <option value="">All</option>
            <option value="lichess_online">Online</option>
            <option value="lichess_study">Study</option>
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="f-color">Color</label>
          <select
            id="f-color"
            value={filters.color}
            onChange={(e) => setFilters({ color: e.target.value, page: '1' })}
          >
            <option value="">Both</option>
            <option value="white">White</option>
            <option value="black">Black</option>
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="f-result">Result</label>
          <select
            id="f-result"
            value={filters.result}
            onChange={(e) => setFilters({ result: e.target.value, page: '1' })}
          >
            <option value="">Any</option>
            <option value="1-0">1-0</option>
            <option value="0-1">0-1</option>
            <option value="1/2-1/2">½-½</option>
            <option value="*">*</option>
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="f-from">From</label>
          <input
            id="f-from"
            type="date"
            value={filters.from}
            onChange={(e) => setFilters({ from: e.target.value, page: '1' })}
          />
        </div>

        <div className="filter-group">
          <label htmlFor="f-to">To</label>
          <input
            id="f-to"
            type="date"
            value={filters.to}
            onChange={(e) => setFilters({ to: e.target.value, page: '1' })}
          />
        </div>

        <button
          type="button"
          onClick={() =>
            setFilters({ source: '', color: '', result: '', from: '', to: '', page: '1' })
          }
        >
          Clear
        </button>
      </div>

      {query.isError && (
        <div className="error">Failed to load games: {String(query.error)}</div>
      )}

      {!query.isError && (
        <div className="table-wrap">
          {items.length === 0 && !query.isPending ? (
            <div className="empty">
              No games match these filters. Import some via{' '}
              <code>POST /api/v1/games/import</code>.
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Played</th>
                  <th>White</th>
                  <th>Black</th>
                  <th>Result</th>
                  <th>You</th>
                  <th>Source</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map((g) => (
                  <tr key={g.id}>
                    <td>{formatDate(g.played_at)}</td>
                    <td>
                      <Link to={`/games/${g.id}`}>{g.white}</Link>{' '}
                      {g.white_elo ? <span className="muted">({g.white_elo})</span> : null}
                    </td>
                    <td>
                      {g.black}{' '}
                      {g.black_elo ? <span className="muted">({g.black_elo})</span> : null}
                    </td>
                    <td>{g.result}</td>
                    <td>{g.user_color}</td>
                    <td>{g.source}</td>
                    <td className="muted">{statusLabel(g)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <div className="pagination">
        <span className="muted">
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
