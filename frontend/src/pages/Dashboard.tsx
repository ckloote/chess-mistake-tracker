import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  AWARENESS_LABELS,
  SEVERITY_COLOR,
  SEVERITY_GLYPH,
  SEVERITY_ORDER,
  STEP_LABELS,
  usePrescription,
  useSummary,
  type StatsSummary,
} from '../api/stats'

const STEP_BAR_COLOR = '#2a4d75' // --ink-azure

const TOOLTIP_STYLE = {
  background: '#faf4e6',
  border: '1px solid #c9bda5',
  borderRadius: 2,
  fontFamily: "'JetBrains Mono', ui-monospace, monospace",
  fontSize: 12,
  color: '#181614',
}

function severityCount(summary: StatsSummary, sev: string): number {
  return summary.by_severity.find((s) => s.severity === sev)?.count ?? 0
}

export function Dashboard() {
  const summaryQuery = useSummary()
  const prescriptionQuery = usePrescription(3)

  if (summaryQuery.isPending) {
    return (
      <DashboardShell>
        <p className="muted">Loading…</p>
      </DashboardShell>
    )
  }
  if (summaryQuery.isError || !summaryQuery.data) {
    return (
      <DashboardShell>
        <div className="error">
          Failed to load stats: {String(summaryQuery.error)}
        </div>
      </DashboardShell>
    )
  }

  const s = summaryQuery.data

  if (s.total_mistakes === 0) {
    return (
      <DashboardShell>
        <div className="placeholder">
          <span className="placeholder-tag">No data yet</span>
          <p>
            No mistakes analyzed yet. Import and analyze games, then classify
            them to populate your patterns here.
          </p>
          <p className="footnote">
            Start at <Link to="/games">Games</Link>.
          </p>
        </div>
      </DashboardShell>
    )
  }

  const classifiedPct =
    s.total_mistakes > 0
      ? Math.round((s.classified / s.total_mistakes) * 100)
      : 0

  const stepData = [...s.by_classified_step]
    .sort((a, b) => a.step - b.step)
    .map((d) => ({
      label: STEP_LABELS[d.step] ?? `Step ${d.step}`,
      step: d.step,
      count: d.count,
    }))

  const prescription = prescriptionQuery.data
  const top = prescription?.items[0]
  const rest = prescription?.items.slice(1) ?? []

  return (
    <DashboardShell>
      {/* Stat cards */}
      <div className="dash-cards">
        <StatCard num={s.total_games} label="Games" />
        <StatCard num={s.total_mistakes} label="Mistakes" />
        <StatCard
          num={`${classifiedPct}%`}
          label="Classified"
          sub={s.unclassified > 0 ? `${s.unclassified} to go` : 'all done'}
        />
        <div className="stat-card">
          <div className="stat-severity">
            {SEVERITY_ORDER.map((sev) => (
              <span key={sev} className="sev-chip">
                <span
                  className="sev-glyph"
                  style={{ color: SEVERITY_COLOR[sev] }}
                >
                  {SEVERITY_GLYPH[sev]}
                </span>
                <span className="sev-num">{severityCount(s, sev)}</span>
              </span>
            ))}
          </div>
          <div className="stat-card-label">Severity</div>
        </div>
      </div>

      {/* Training prescription */}
      {top && (
        <section className="dash-section">
          <h2>Train this first</h2>
          <div className="rx-top">
            <div className="rx-top-head">
              <span className="rx-rank">#1 pattern</span>
              <span className="rx-share">
                {Math.round(top.share * 100)}% of classified
              </span>
            </div>
            <div className="rx-pattern">
              {STEP_LABELS[top.step] ?? `Step ${top.step}`}
              <span className="rx-sep"> · </span>
              <span className="rx-aware">
                {AWARENESS_LABELS[top.awareness] ?? top.awareness}
              </span>
              <span className="rx-count"> ({top.count})</span>
            </div>
            <p className="rx-suggestion">{top.suggestion}</p>
          </div>

          {rest.length > 0 && (
            <ol className="rx-list">
              {rest.map((item, i) => (
                <li key={i} className="rx-item">
                  <span className="rx-item-rank">#{i + 2}</span>
                  <span className="rx-item-pattern">
                    {STEP_LABELS[item.step] ?? `Step ${item.step}`} ·{' '}
                    {AWARENESS_LABELS[item.awareness] ?? item.awareness}
                  </span>
                  <span className="rx-item-share">
                    {Math.round(item.share * 100)}%
                  </span>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}

      {/* Step distribution */}
      <section className="dash-section">
        <h2>Mistake types</h2>
        <p className="dash-section-note">
          Your classified Layer A step for every mistake.
        </p>
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={stepData}
              layout="vertical"
              margin={{ top: 4, right: 36, bottom: 4, left: 8 }}
            >
              <XAxis type="number" allowDecimals={false} hide />
              <YAxis
                type="category"
                dataKey="label"
                width={150}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 12, fill: '#6e6457' }}
              />
              <Tooltip cursor={{ fill: '#ece4d2' }} contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="count" radius={[0, 2, 2, 0]} maxBarSize={26}>
                {stepData.map((d) => (
                  <Cell key={d.step} fill={STEP_BAR_COLOR} />
                ))}
                <LabelList
                  dataKey="count"
                  position="right"
                  style={{
                    fill: '#181614',
                    fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                    fontSize: 12,
                  }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <p className="dash-more muted">
        More breakdowns on the <Link to="/stats">Stats</Link> page · review the{' '}
        <Link to="/mistakes">queue</Link>.
      </p>
    </DashboardShell>
  )
}

function DashboardShell({ children }: { children: ReactNode }) {
  return (
    <div>
      <div className="page-header">
        <div className="page-header-title">
          <span className="eyebrow">Index</span>
          <h1>Dashboard</h1>
        </div>
      </div>
      {children}
    </div>
  )
}

function StatCard({
  num,
  label,
  sub,
}: {
  num: number | string
  label: string
  sub?: string
}) {
  return (
    <div className="stat-card">
      <div className="stat-card-num">{num}</div>
      <div className="stat-card-label">{label}</div>
      {sub && <div className="stat-card-sub">{sub}</div>}
    </div>
  )
}
