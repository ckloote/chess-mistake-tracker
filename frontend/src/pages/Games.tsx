import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useUrlState } from '../hooks/useUrlState'
import {
  useAnalyzeGame,
  useAnalyzePending,
  useGamesList,
  useImportGames,
  useRefreshGame,
  type Game,
  type GameFilters,
} from '../api/games'

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

interface GameStatus {
  label: string
  className: string
}

function gameStatus(g: { has_evals: boolean; analyzed_at: string | null }): GameStatus {
  if (g.analyzed_at) return { label: 'Analyzed', className: 'analyzed' }
  if (g.has_evals) return { label: 'Pending', className: 'pending' }
  return { label: 'Needs Lichess analysis', className: 'needs' }
}

// Link to the game at its source — for online games this is also where the
// user clicks "Request computer analysis" before refreshing.
function lichessUrl(g: Game): string {
  if (g.source === 'lichess_study') {
    const [studyId, chapterId] = g.source_game_id.split(':')
    return `https://lichess.org/study/${studyId}/${chapterId ?? ''}`
  }
  return `https://lichess.org/${g.source_game_id}`
}

export function Games() {
  const [filters, setFilters] = useUrlState<FilterKey>(FILTER_DEFAULTS)
  const apiFilters = toApiFilters(filters)
  const query = useGamesList(apiFilters)

  const importGames = useImportGames()
  const analyzePending = useAnalyzePending()
  const analyzeGame = useAnalyzeGame()
  const refreshGame = useRefreshGame()

  const [importSource, setImportSource] = useState('lichess_online')
  const [importMax, setImportMax] = useState('30')

  function runImport() {
    const limit = Number.parseInt(importMax, 10)
    importGames.mutate({
      source: importSource,
      // Studies have no meaningful limit; only send one for online games.
      ...(importSource === 'lichess_online' && Number.isFinite(limit) && limit > 0
        ? { limit }
        : {}),
    })
  }

  // Collect the first action error for the shared error line below the bar.
  const actionError =
    importGames.error ?? analyzePending.error ?? analyzeGame.error ?? refreshGame.error

  const total = query.data?.total ?? 0
  const items = query.data?.items ?? []
  const page = apiFilters.page ?? 1
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div>
      <div className="page-header">
        <div className="page-header-title">
          <span className="eyebrow">Archive</span>
          <h1>Games</h1>
        </div>
        <span className="page-header-meta">
          {query.isPending
            ? 'loading…'
            : `${total} ${total === 1 ? 'game' : 'games'}`}
        </span>
      </div>

      <div className="games-actions">
        <div className="filter-group">
          <label htmlFor="i-source">Import from</label>
          <select
            id="i-source"
            value={importSource}
            onChange={(e) => setImportSource(e.target.value)}
          >
            <option value="lichess_online">Lichess games</option>
            <option value="lichess_study">Lichess studies</option>
          </select>
        </div>
        {importSource === 'lichess_online' && (
          <div className="filter-group">
            <label htmlFor="i-max">Max games</label>
            <input
              id="i-max"
              type="number"
              min={1}
              max={500}
              value={importMax}
              onChange={(e) => setImportMax(e.target.value)}
            />
          </div>
        )}
        <button type="button" onClick={runImport} disabled={importGames.isPending}>
          {importGames.isPending ? 'Importing…' : 'Import'}
        </button>
        <button
          type="button"
          onClick={() => analyzePending.mutate({})}
          disabled={analyzePending.isPending}
          title="Analyze every imported game that has evals but hasn't been analyzed yet"
        >
          {analyzePending.isPending ? 'Analyzing…' : 'Analyze pending'}
        </button>
        {importGames.isSuccess && !importGames.isPending && (
          <span className="games-action-result">
            imported {importGames.data.imported}, skipped {importGames.data.skipped}
          </span>
        )}
        {analyzePending.isSuccess && !analyzePending.isPending && (
          <span className="games-action-result">
            analyzed {analyzePending.data.analyzed}
            {analyzePending.data.skipped > 0
              ? `, skipped ${analyzePending.data.skipped}`
              : ''}
          </span>
        )}
      </div>
      {actionError != null && (
        <div className="error" style={{ marginBottom: 16 }}>
          {String(actionError)}
        </div>
      )}

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
            <option value="1-0">1–0</option>
            <option value="0-1">0–1</option>
            <option value="1/2-1/2">½–½</option>
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
            setFilters({
              source: '',
              color: '',
              result: '',
              from: '',
              to: '',
              page: '1',
            })
          }
        >
          Clear
        </button>
      </div>

      {query.isError && (
        <div className="error">Failed to load games: {String(query.error)}</div>
      )}

      {!query.isError && (
        <div className="games-table-wrap">
          {items.length === 0 && !query.isPending ? (
            <div className="empty">
              <p style={{ margin: 0 }}>No games in the archive yet.</p>
              <p
                style={{
                  margin: '12px 0 0',
                  fontFamily: 'var(--font-body)',
                  fontStyle: 'normal',
                  fontSize: '0.85rem',
                }}
                className="muted"
              >
                Use the Import controls above to pull your games from Lichess.
              </p>
            </div>
          ) : (
            <table className="games-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>White</th>
                  <th>Black</th>
                  <th>Result</th>
                  <th>You</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((g) => {
                  const status = gameStatus(g)
                  return (
                    <tr key={g.id}>
                      <td className="cell-date">{formatDate(g.played_at)}</td>
                      <td className="cell-player">
                        <Link to={`/games/${g.id}`}>{g.white}</Link>
                        {g.white_elo ? (
                          <span className="cell-elo">{g.white_elo}</span>
                        ) : null}
                      </td>
                      <td className="cell-player">
                        {g.black}
                        {g.black_elo ? (
                          <span className="cell-elo">{g.black_elo}</span>
                        ) : null}
                      </td>
                      <td className="cell-result">{g.result.replace(/-/g, '–')}</td>
                      <td>
                        <span className={`cell-color ${g.user_color}`}>
                          {g.user_color}
                        </span>
                      </td>
                      <td className="cell-source">
                        {g.source.replace('lichess_', '')}
                      </td>
                      <td>
                        <span className={`status-pill ${status.className}`}>
                          {status.label}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        {status.className === 'pending' && (
                          <button
                            type="button"
                            className="row-action"
                            onClick={() => analyzeGame.mutate(g.id)}
                            disabled={
                              analyzeGame.isPending && analyzeGame.variables === g.id
                            }
                          >
                            {analyzeGame.isPending && analyzeGame.variables === g.id
                              ? 'Analyzing…'
                              : 'Analyze'}
                          </button>
                        )}
                        {status.className === 'needs' && (
                          <>
                            <a
                              className="row-link"
                              href={lichessUrl(g)}
                              target="_blank"
                              rel="noreferrer"
                              title="Open on Lichess and click 'Request a computer analysis', then Refresh here"
                            >
                              Request&nbsp;↗
                            </a>
                            <button
                              type="button"
                              className="row-action"
                              onClick={() => refreshGame.mutate(g.id)}
                              disabled={
                                refreshGame.isPending && refreshGame.variables === g.id
                              }
                              title="Re-fetch this game from Lichess to pick up analysis"
                            >
                              {refreshGame.isPending && refreshGame.variables === g.id
                                ? 'Refreshing…'
                                : 'Refresh'}
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  )
                })}
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
