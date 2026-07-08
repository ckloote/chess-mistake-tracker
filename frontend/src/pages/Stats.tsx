import type { ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useUrlState } from '../hooks/useUrlState'
import {
  AWARENESS_LABELS,
  STEP_LABELS,
  useBreakdown,
  useSummary,
  type BreakdownItem,
  type StatsFilters,
} from '../api/stats'

const TOOLTIP_STYLE = {
  background: '#faf4e6',
  border: '1px solid #c9bda5',
  borderRadius: 2,
  fontFamily: "'JetBrains Mono', ui-monospace, monospace",
  fontSize: 12,
  color: '#181614',
}

const PHASE_LABELS: Record<string, string> = {
  middlegame_or_opening: 'Opening / Middlegame',
  endgame: 'Endgame',
}
const TIME_LABELS: Record<string, string> = {
  normal: 'Normal',
  time_pressure: 'Time pressure',
}

const AWARENESS_COLS = ['didnt_see_it', 'got_it_wrong'] as const

// All-empty defaults: the unfiltered page is the canonical URL (no params).
const FILTER_DEFAULTS = {
  from: '',
  to: '',
  source: '',
  color: '',
  severity: '',
  speed: '',
} as const

type FilterKey = keyof typeof FILTER_DEFAULTS

function toApiFilters(s: Record<FilterKey, string>): StatsFilters {
  const out: StatsFilters = {}
  if (s.from) out.from = s.from
  if (s.to) out.to = s.to
  if (s.source) out.source = s.source
  if (s.color) out.color = s.color
  if (s.severity) out.severity = s.severity
  if (s.speed) out.speed = s.speed
  return out
}

export function Stats() {
  const [filters, setFilters] = useUrlState<FilterKey>(FILTER_DEFAULTS)
  const apiFilters = toApiFilters(filters)
  const filtersActive = Object.keys(apiFilters).length > 0

  const summaryQuery = useSummary(apiFilters)
  const cross = useBreakdown('step_x_awareness', apiFilters)
  const phase = useBreakdown('phase', apiFilters)
  const timePressure = useBreakdown('time_pressure', apiFilters)
  const month = useBreakdown('month', apiFilters)

  const s = summaryQuery.data
  const meta = summaryQuery.isPending
    ? 'loading…'
    : s
      ? `${s.total_games} ${s.total_games === 1 ? 'game' : 'games'} · ` +
        `${s.total_mistakes} ${s.total_mistakes === 1 ? 'mistake' : 'mistakes'}`
      : ''

  const filterBar = (
    <FilterBar
      filters={filters}
      setFilters={setFilters}
      filtersActive={filtersActive}
    />
  )

  if (summaryQuery.isPending) {
    return (
      <StatsShell meta={meta}>
        {filterBar}
        <p className="muted">Loading…</p>
      </StatsShell>
    )
  }
  if (summaryQuery.isError || !s) {
    return (
      <StatsShell meta={meta}>
        {filterBar}
        <div className="error">
          Failed to load stats: {String(summaryQuery.error)}
        </div>
      </StatsShell>
    )
  }
  if (s.total_mistakes === 0) {
    return (
      <StatsShell meta={meta}>
        {filterBar}
        <div className="placeholder">
          {filtersActive ? (
            <p>No mistakes match these filters.</p>
          ) : (
            <>
              <span className="placeholder-tag">No data yet</span>
              <p>Analyze and classify some games to see your patterns here.</p>
            </>
          )}
        </div>
      </StatsShell>
    )
  }

  return (
    <StatsShell meta={meta}>
      {filterBar}
      <section className="dash-section">
        <h2>Where your mistakes cluster</h2>
        <p className="dash-section-note">
          Layer A (mistake type) × Layer B (were you aware?). Darker = more
          frequent — your study priorities live in the dark cells.
        </p>
        <Heatmap items={cross.data?.items ?? []} />
      </section>

      <section className="dash-section">
        <h2>Heuristic vs. you</h2>
        <p className="dash-section-note">
          The auto-suggested Step vs. how you actually classified — a read on how
          well the Layer A heuristic predicts your judgment.
        </p>
        <SuggestedVsClassified
          suggested={s.by_suggested_step}
          classified={s.by_classified_step}
        />
      </section>

      <div className="stats-two-up">
        <section className="dash-section">
          <h2>By game phase</h2>
          <MiniBars items={phase.data?.items ?? []} labels={PHASE_LABELS} />
        </section>
        <section className="dash-section">
          <h2>By time pressure</h2>
          <MiniBars
            items={timePressure.data?.items ?? []}
            labels={TIME_LABELS}
          />
        </section>
      </div>

      <section className="dash-section">
        <h2>Mistakes over time</h2>
        <MonthChart items={month.data?.items ?? []} />
      </section>
    </StatsShell>
  )
}

// ---- Filter bar -------------------------------------------------------------

function FilterBar({
  filters,
  setFilters,
  filtersActive,
}: {
  filters: Record<FilterKey, string>
  setFilters: (patch: Partial<Record<FilterKey, string>>) => void
  filtersActive: boolean
}) {
  return (
    <div className="filters">
      <div className="filter-group">
        <label htmlFor="sf-from">From</label>
        <input
          id="sf-from"
          type="date"
          value={filters.from}
          onChange={(e) => setFilters({ from: e.target.value })}
        />
      </div>

      <div className="filter-group">
        <label htmlFor="sf-to">To</label>
        <input
          id="sf-to"
          type="date"
          value={filters.to}
          onChange={(e) => setFilters({ to: e.target.value })}
        />
      </div>

      <div className="filter-group">
        <label htmlFor="sf-source">Source</label>
        <select
          id="sf-source"
          value={filters.source}
          onChange={(e) => setFilters({ source: e.target.value })}
        >
          <option value="">Any</option>
          <option value="lichess_online">Lichess games</option>
          <option value="lichess_study">Lichess studies</option>
        </select>
      </div>

      <div className="filter-group">
        <label htmlFor="sf-color">Color</label>
        <select
          id="sf-color"
          value={filters.color}
          onChange={(e) => setFilters({ color: e.target.value })}
        >
          <option value="">Any</option>
          <option value="white">White</option>
          <option value="black">Black</option>
        </select>
      </div>

      <div className="filter-group">
        <label htmlFor="sf-severity">Severity</label>
        <select
          id="sf-severity"
          value={filters.severity}
          onChange={(e) => setFilters({ severity: e.target.value })}
        >
          <option value="">Any</option>
          <option value="blunder">Blunder ??</option>
          <option value="mistake">Mistake ?</option>
          <option value="inaccuracy">Inaccuracy ?!</option>
        </select>
      </div>

      <div className="filter-group">
        <label htmlFor="sf-speed">Speed</label>
        <select
          id="sf-speed"
          value={filters.speed}
          onChange={(e) => setFilters({ speed: e.target.value })}
        >
          <option value="">Any</option>
          <option value="bullet">Bullet</option>
          <option value="blitz">Blitz</option>
          <option value="rapid">Rapid</option>
          <option value="classical">Classical</option>
          <option value="unknown">No clock (OTB)</option>
        </select>
      </div>

      {filtersActive && (
        <button
          type="button"
          onClick={() =>
            setFilters({
              from: '',
              to: '',
              source: '',
              color: '',
              severity: '',
              speed: '',
            })
          }
        >
          Reset
        </button>
      )}
    </div>
  )
}

// ---- Step × Awareness heatmap ---------------------------------------------

function parseCell(label: string): { step: number; awareness: string } {
  const [stepPart, awareness] = label.split('|')
  return {
    step: Number.parseInt((stepPart ?? '').replace('step_', ''), 10),
    awareness: awareness ?? '',
  }
}

function Heatmap({ items }: { items: BreakdownItem[] }) {
  if (items.length === 0) return <p className="muted">No classified data.</p>

  const counts = new Map<string, number>()
  const steps = new Set<number>()
  for (const it of items) {
    const { step, awareness } = parseCell(it.label)
    if (!Number.isFinite(step)) continue
    counts.set(`${step}|${awareness}`, it.count)
    steps.add(step)
  }
  const stepRows = [...steps].sort((a, b) => a - b)
  const max = Math.max(1, ...items.map((i) => i.count))

  return (
    <div
      className="heatmap"
      style={{
        gridTemplateColumns: `minmax(160px, 1.4fr) repeat(${AWARENESS_COLS.length}, 1fr)`,
      }}
    >
      <div className="hm-corner" />
      {AWARENESS_COLS.map((a) => (
        <div key={a} className="hm-colhead">
          {AWARENESS_LABELS[a] ?? a}
        </div>
      ))}

      {stepRows.map((step) => (
        <Row key={step}>
          <div className="hm-rowhead">
            <span className="hm-step-no">{step}</span>
            {STEP_LABELS[step] ?? `Step ${step}`}
          </div>
          {AWARENESS_COLS.map((a) => {
            const c = counts.get(`${step}|${a}`) ?? 0
            const intensity = c === 0 ? 0 : 0.12 + 0.78 * (c / max)
            return (
              <div
                key={a}
                className="hm-cell"
                style={{
                  background: `rgba(122, 26, 31, ${intensity})`,
                  color: intensity > 0.45 ? '#faf4e6' : '#181614',
                }}
              >
                {c > 0 ? c : ''}
              </div>
            )
          })}
        </Row>
      ))}
    </div>
  )
}

// React fragment that renders grid children in order (the grid is the parent).
function Row({ children }: { children: ReactNode }) {
  return <>{children}</>
}

// ---- Suggested vs classified grouped bars ---------------------------------

function SuggestedVsClassified({
  suggested,
  classified,
}: {
  suggested: { step: number; count: number }[]
  classified: { step: number; count: number }[]
}) {
  const steps = [1, 2, 3, 4]
  const sMap = new Map(suggested.map((d) => [d.step, d.count]))
  const cMap = new Map(classified.map((d) => [d.step, d.count]))
  const data = steps.map((step) => ({
    label: `${step}. ${STEP_LABELS[step] ?? ''}`.trim(),
    Suggested: sMap.get(step) ?? 0,
    Classified: cMap.get(step) ?? 0,
  }))

  return (
    <div className="chart-wrap chart-tall">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
          <CartesianGrid stroke="#ddd1b9" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 11, fill: '#6e6457' }}
            tickLine={false}
            axisLine={{ stroke: '#c9bda5' }}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontSize: 11, fill: '#6e6457' }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip cursor={{ fill: '#ece4d2' }} contentStyle={TOOLTIP_STYLE} />
          <Legend wrapperStyle={{ fontSize: 12, fontFamily: 'Instrument Sans, sans-serif' }} />
          <Bar dataKey="Suggested" fill="#9a8f7e" radius={[2, 2, 0, 0]} maxBarSize={40} />
          <Bar dataKey="Classified" fill="#2a4d75" radius={[2, 2, 0, 0]} maxBarSize={40} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ---- Mini proportional bar list (phase / time pressure) -------------------

function MiniBars({
  items,
  labels,
}: {
  items: BreakdownItem[]
  labels: Record<string, string>
}) {
  if (items.length === 0) return <p className="muted">No data.</p>
  const total = items.reduce((a, b) => a + b.count, 0) || 1
  return (
    <div className="minibars">
      {items.map((it) => {
        const pct = Math.round((it.count / total) * 100)
        return (
          <div key={it.label} className="minibar-row">
            <span className="minibar-label">{labels[it.label] ?? it.label}</span>
            <span className="minibar-track">
              <span className="minibar-fill" style={{ width: `${pct}%` }} />
            </span>
            <span className="minibar-val">
              {it.count} <span className="minibar-pct">{pct}%</span>
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ---- Mistakes over time ----------------------------------------------------

function MonthChart({ items }: { items: BreakdownItem[] }) {
  const unknown = items.find((i) => i.label === 'unknown')?.count ?? 0
  const data = items
    .filter((i) => i.label !== 'unknown')
    .sort((a, b) => a.label.localeCompare(b.label))
    .map((i) => ({ label: i.label, count: i.count }))

  if (data.length === 0) {
    return <p className="muted">No dated games yet.</p>
  }

  return (
    <>
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
            <CartesianGrid stroke="#ddd1b9" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: '#6e6457' }}
              tickLine={false}
              axisLine={{ stroke: '#c9bda5' }}
            />
            <YAxis
              allowDecimals={false}
              tick={{ fontSize: 11, fill: '#6e6457' }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip cursor={{ fill: '#ece4d2' }} contentStyle={TOOLTIP_STYLE} />
            <Bar dataKey="count" fill="#3a6635" radius={[2, 2, 0, 0]} maxBarSize={48} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {unknown > 0 && (
        <p className="dash-section-note" style={{ marginTop: 8 }}>
          {unknown} mistake{unknown === 1 ? '' : 's'} from games with no recorded
          date are not shown.
        </p>
      )}
    </>
  )
}

function StatsShell({ meta, children }: { meta?: string; children: ReactNode }) {
  return (
    <div>
      <div className="page-header">
        <div className="page-header-title">
          <span className="eyebrow">Analysis</span>
          <h1>Patterns</h1>
        </div>
        {meta && <span className="page-header-meta">{meta}</span>}
      </div>
      {children}
    </div>
  )
}
