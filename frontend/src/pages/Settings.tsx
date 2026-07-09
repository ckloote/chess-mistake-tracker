import { useMemo, useState } from 'react'
import {
  DETECTION_FIELDS,
  useSettings,
  useUpdateSettings,
  type AppSettings,
  type SettingsUpdate,
} from '../api/settings'
import { useAnalyzePending, type AnalyzePendingResult } from '../api/games'

// Local, editable mirror of the server settings. Numbers are kept as strings
// while editing so partial input ("7.") doesn't fight the user; parsed on save.
interface FormState {
  winrate_inaccuracy: string
  winrate_mistake: string
  winrate_blunder: string
  suppress_below: string
  suppress_above_before: string
  suppress_above_after: string
  study_ids: string // comma-separated in the UI
  aliases: string
  chesscom_username: string
}

function toForm(s: AppSettings): FormState {
  return {
    winrate_inaccuracy: String(s.winrate_inaccuracy),
    winrate_mistake: String(s.winrate_mistake),
    winrate_blunder: String(s.winrate_blunder),
    suppress_below: String(s.suppress_below),
    suppress_above_before: String(s.suppress_above_before),
    suppress_above_after: String(s.suppress_above_after),
    study_ids: s.lichess_study_ids.join(', '),
    aliases: s.study_player_aliases.join(', '),
    chesscom_username: s.chesscom_username ?? '',
  }
}

function splitCsv(value: string): string[] {
  return value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

function toPayload(form: FormState): SettingsUpdate | { error: string } {
  const numbers: Record<string, number> = {}
  const numericFields: [keyof FormState, string][] = [
    ['winrate_inaccuracy', 'Inaccuracy threshold'],
    ['winrate_mistake', 'Mistake threshold'],
    ['winrate_blunder', 'Blunder threshold'],
    ['suppress_below', 'Already-losing bound'],
    ['suppress_above_before', 'Still-winning bound (before)'],
    ['suppress_above_after', 'Still-winning bound (after)'],
  ]
  for (const [key, label] of numericFields) {
    const parsed = Number.parseFloat(form[key])
    if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100) {
      return { error: `${label} must be a number between 0 and 100.` }
    }
    numbers[key] = parsed
  }
  return {
    ...numbers,
    lichess_study_ids: splitCsv(form.study_ids),
    study_player_aliases: splitCsv(form.aliases),
    chesscom_username: form.chesscom_username.trim() || null,
  }
}

function extractDetail(err: unknown): string {
  if (err && typeof err === 'object' && 'detail' in err) {
    const detail = (err as { detail?: unknown }).detail
    if (typeof detail === 'object' && detail !== null && 'detail' in detail) {
      const inner = (detail as { detail?: unknown }).detail
      if (typeof inner === 'string') return inner
      // Pydantic 422s carry a list of {msg, ...} objects.
      if (Array.isArray(inner)) {
        const msgs = inner
          .map((e) => (e && typeof e === 'object' && 'msg' in e ? String(e.msg) : null))
          .filter(Boolean)
        if (msgs.length > 0) return msgs.join('; ')
      }
    }
  }
  return String(err)
}

export function Settings() {
  const settingsQuery = useSettings()
  const update = useUpdateSettings()
  const reanalyze = useAnalyzePending()

  const [form, setForm] = useState<FormState | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [needsReanalysis, setNeedsReanalysis] = useState(false)
  const [reanalyzeResult, setReanalyzeResult] = useState<AnalyzePendingResult | null>(null)

  // Initialize (and re-sync after saves) from the server state. Render-time
  // adjustment instead of an effect, per react.dev "adjusting state when
  // props change" — avoids a cascading re-render.
  const [syncedFrom, setSyncedFrom] = useState<AppSettings | null>(null)
  if (settingsQuery.data && settingsQuery.data !== syncedFrom) {
    setSyncedFrom(settingsQuery.data)
    setForm(toForm(settingsQuery.data))
  }

  const set = (patch: Partial<FormState>) => {
    setForm((f) => (f ? { ...f, ...patch } : f))
    setFormError(null)
  }

  const dirty = useMemo(() => {
    if (!form || !settingsQuery.data) return false
    return JSON.stringify(form) !== JSON.stringify(toForm(settingsQuery.data))
  }, [form, settingsQuery.data])

  function save() {
    if (!form || !settingsQuery.data) return
    const payload = toPayload(form)
    if ('error' in payload) {
      setFormError(payload.error)
      return
    }
    const before = settingsQuery.data
    update.mutate(payload, {
      onSuccess: (after) => {
        // Warn when a detection-affecting knob actually changed — existing
        // Mistake rows were derived under the old rules.
        const detectionChanged = DETECTION_FIELDS.some(
          (key) => before[key] !== after[key],
        )
        if (detectionChanged) {
          setNeedsReanalysis(true)
          setReanalyzeResult(null)
        }
      },
    })
  }

  function runReanalyze() {
    reanalyze.mutate(
      { force: true },
      {
        onSuccess: (result) => {
          setReanalyzeResult(result)
          setNeedsReanalysis(false)
        },
      },
    )
  }

  if (settingsQuery.isPending || !form) {
    return (
      <SettingsShell>
        <p className="muted">Loading…</p>
      </SettingsShell>
    )
  }
  if (settingsQuery.isError) {
    return (
      <SettingsShell>
        <div className="error">
          Failed to load settings: {String(settingsQuery.error)}
        </div>
      </SettingsShell>
    )
  }

  const username = settingsQuery.data?.lichess_username

  const totals = reanalyzeResult
    ? reanalyzeResult.results.reduce(
        (acc, r) => ({
          new: acc.new + r.mistakes_new,
          updated: acc.updated + r.mistakes_updated,
          removed: acc.removed + r.mistakes_removed,
          preserved: acc.preserved + r.mistakes_preserved,
        }),
        { new: 0, updated: 0, removed: 0, preserved: 0 },
      )
    : null

  return (
    <SettingsShell>
      {needsReanalysis && (
        <div className="settings-banner">
          <span>
            Detection rules changed — existing mistakes were derived under the
            old rules. Re-analyze to apply them (your classifications are
            preserved).
          </span>
          <button
            type="button"
            className="settings-banner-action"
            onClick={runReanalyze}
            disabled={reanalyze.isPending}
          >
            {reanalyze.isPending ? 'Re-analyzing…' : 'Re-analyze all games'}
          </button>
        </div>
      )}

      <section className="dash-section">
        <h2>Account</h2>
        <div className="settings-grid">
          <div className="filter-group">
            <label htmlFor="s-username">Lichess username</label>
            <input id="s-username" type="text" value={username ?? ''} disabled />
            <span className="settings-hint">
              From <code>.env</code> — changing it means re-seeding the database.
            </span>
          </div>
          <div className="filter-group">
            <label htmlFor="s-chesscom">chess.com username</label>
            <input
              id="s-chesscom"
              type="text"
              value={form.chesscom_username}
              placeholder="e.g. hikaru"
              onChange={(e) => set({ chesscom_username: e.target.value })}
            />
            <span className="settings-hint">
              Used by the chess.com import; seeded from <code>.env</code> on
              first run.
            </span>
          </div>
          <div className="filter-group">
            <label htmlFor="s-engine">Local Stockfish</label>
            <input
              id="s-engine"
              type="text"
              value={
                settingsQuery.data?.stockfish_available
                  ? 'Available'
                  : 'Not found'
              }
              disabled
            />
            <span className="settings-hint">
              {settingsQuery.data?.stockfish_available
                ? 'Games without Lichess evals are analyzed locally; the Explore board is live.'
                : 'Install stockfish (or set STOCKFISH_PATH) to analyze games without Lichess evals.'}
            </span>
          </div>
        </div>
      </section>

      <section className="dash-section">
        <h2>Detection thresholds</h2>
        <p className="dash-section-note">
          Win%-drop needed to flag a move. A drop below the inaccuracy bound is
          ignored.
        </p>
        <div className="settings-grid">
          <NumberField
            id="s-inacc"
            label="Inaccuracy ≥"
            value={form.winrate_inaccuracy}
            onChange={(v) => set({ winrate_inaccuracy: v })}
          />
          <NumberField
            id="s-mistake"
            label="Mistake ≥"
            value={form.winrate_mistake}
            onChange={(v) => set({ winrate_mistake: v })}
          />
          <NumberField
            id="s-blunder"
            label="Blunder ≥"
            value={form.winrate_blunder}
            onChange={(v) => set({ winrate_blunder: v })}
          />
        </div>
      </section>

      <section className="dash-section">
        <h2>Suppression</h2>
        <p className="dash-section-note">
          Skip slips that don't cost a usable advantage: positions already lost
          (both win% below the first bound), and inaccuracies while still
          comfortably winning (win% above the before/after bounds).
        </p>
        <div className="settings-grid">
          <NumberField
            id="s-below"
            label="Already losing <"
            value={form.suppress_below}
            onChange={(v) => set({ suppress_below: v })}
          />
          <NumberField
            id="s-above-b"
            label="Still winning: before >"
            value={form.suppress_above_before}
            onChange={(v) => set({ suppress_above_before: v })}
          />
          <NumberField
            id="s-above-a"
            label="Still winning: after >"
            value={form.suppress_above_after}
            onChange={(v) => set({ suppress_above_after: v })}
          />
        </div>
      </section>

      <section className="dash-section">
        <h2>Studies</h2>
        <p className="dash-section-note">
          Lichess study IDs to import (8 characters each), and the names your
          OTB games record you under. Comma-separated. Takes effect on the next
          import.
        </p>
        <div className="settings-grid settings-grid-wide">
          <div className="filter-group">
            <label htmlFor="s-studies">Study IDs</label>
            <input
              id="s-studies"
              type="text"
              value={form.study_ids}
              placeholder="e.g. 0cI2EWNC, a1B2c3D4"
              onChange={(e) => set({ study_ids: e.target.value })}
            />
          </div>
          <div className="filter-group">
            <label htmlFor="s-aliases">Player aliases</label>
            <input
              id="s-aliases"
              type="text"
              value={form.aliases}
              placeholder="e.g. CJK, C. Kloote"
              onChange={(e) => set({ aliases: e.target.value })}
            />
          </div>
        </div>
      </section>

      {formError && <div className="error">{formError}</div>}
      {update.isError && (
        <div className="error">Save failed: {extractDetail(update.error)}</div>
      )}

      <div className="settings-actions">
        <button
          type="button"
          className="settings-save"
          onClick={save}
          disabled={!dirty || update.isPending}
          title={dirty ? 'Save settings' : 'No changes to save'}
        >
          {update.isPending ? 'Saving…' : 'Save settings'}
        </button>
        {!dirty && !update.isPending && update.isSuccess && (
          <span className="muted">Saved.</span>
        )}
      </div>

      <section className="dash-section">
        <h2>Maintenance</h2>
        <p className="dash-section-note">
          Re-runs detection and heuristic suggestions on every analyzed game
          with the current rules. Your classifications and notes survive:
          re-detected mistakes are updated in place, and classified mistakes
          are never deleted.
        </p>
        <div className="settings-actions">
          <button
            type="button"
            onClick={runReanalyze}
            disabled={reanalyze.isPending}
          >
            {reanalyze.isPending ? 'Re-analyzing…' : 'Re-analyze all games'}
          </button>
          {reanalyze.isError && (
            <span className="error settings-inline-error">
              {extractDetail(reanalyze.error)}
            </span>
          )}
        </div>
        {reanalyzeResult && totals && (
          <p className="settings-result">
            Re-analyzed {reanalyzeResult.analyzed}{' '}
            {reanalyzeResult.analyzed === 1 ? 'game' : 'games'}
            {reanalyzeResult.skipped > 0
              ? ` (${reanalyzeResult.skipped} skipped)`
              : ''}
            : {totals.new} new · {totals.updated} updated · {totals.removed}{' '}
            removed · {totals.preserved} preserved-classified.
          </p>
        )}
      </section>
    </SettingsShell>
  )
}

function NumberField({
  id,
  label,
  value,
  onChange,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="filter-group">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="number"
        min={0}
        max={100}
        step={0.5}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

function SettingsShell({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <div className="page-header">
        <div className="page-header-title">
          <span className="eyebrow">Configuration</span>
          <h1>Settings</h1>
        </div>
      </div>
      {children}
    </div>
  )
}
