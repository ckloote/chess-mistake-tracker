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
import {
  AWARENESS_LABELS,
  STEP_LABELS,
  useBreakdown,
  useSummary,
  type BreakdownItem,
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

export function Stats() {
  const summaryQuery = useSummary()
  const cross = useBreakdown('step_x_awareness')
  const phase = useBreakdown('phase')
  const timePressure = useBreakdown('time_pressure')
  const month = useBreakdown('month')

  if (summaryQuery.isPending) {
    return (
      <StatsShell>
        <p className="muted">Loading…</p>
      </StatsShell>
    )
  }
  if (summaryQuery.isError || !summaryQuery.data) {
    return (
      <StatsShell>
        <div className="error">
          Failed to load stats: {String(summaryQuery.error)}
        </div>
      </StatsShell>
    )
  }
  const s = summaryQuery.data
  if (s.total_mistakes === 0) {
    return (
      <StatsShell>
        <div className="placeholder">
          <span className="placeholder-tag">No data yet</span>
          <p>Analyze and classify some games to see your patterns here.</p>
        </div>
      </StatsShell>
    )
  }

  return (
    <StatsShell>
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

function StatsShell({ children }: { children: ReactNode }) {
  return (
    <div>
      <div className="page-header">
        <div className="page-header-title">
          <span className="eyebrow">Analysis</span>
          <h1>Patterns</h1>
        </div>
      </div>
      {children}
    </div>
  )
}
