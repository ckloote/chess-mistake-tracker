import { useEffect, useRef, useState } from 'react'
import type { Mistake } from '../api/games'
import type { MistakeUpdatePayload } from '../api/mistakes'

const STEP_LABELS: Record<number, { title: string; gloss: string }> = {
  1: { title: 'Missed opponent threat', gloss: 'they had a tactical reply I didn’t address' },
  2: { title: 'Missed forcing move', gloss: 'I had a check / capture / threat available' },
  3: { title: 'Strategic inaccuracy', gloss: 'wrong plan in a quiet position' },
  4: { title: 'Failed blunder check', gloss: 'I overlooked their best reply to my move' },
}

interface Props {
  mistake: Mistake
  saving: boolean
  onSave: (payload: MistakeUpdatePayload) => void
  onSkip: () => void
  onBack: () => void
}

interface FormState {
  step: number | null
  awareness: 'got_it_wrong' | 'didnt_see_it' | null
  notes: string
  timePressure: boolean
  transition: boolean
  endgame: boolean
}

// Local form state lives here. Initialized from the mistake row; reset
// whenever the mistake id changes (so navigating in "save & next" loads
// fresh defaults from the next mistake).
function initialState(m: Mistake): FormState {
  return {
    step: m.classified_step ?? m.suggested_step ?? null,
    awareness: m.classified_awareness,
    notes: m.user_notes ?? '',
    timePressure: m.time_pressure_flag,
    transition: m.transition_flag,
    endgame: m.endgame_flag,
  }
}

export function ClassificationForm({
  mistake,
  saving,
  onSave,
  onSkip,
  onBack,
}: Props) {
  const [state, setState] = useState<FormState>(() => initialState(mistake))
  const notesRef = useRef<HTMLTextAreaElement>(null)

  // Reset the form when the mistake id changes — moving between mistakes
  // should NOT carry the previous mistake's local state forward.
  useEffect(() => {
    setState(initialState(mistake))
  }, [mistake.id])

  // The suggested step is only meaningful when the user hasn't picked
  // anything yet (i.e. classified_step is null). Once they classify it,
  // their choice wins.
  const userSelectedStep = mistake.classified_step !== null
  const showSuggested = !userSelectedStep && mistake.suggested_step !== null

  function save() {
    if (state.step === null) return
    onSave({
      classified_step: state.step,
      classified_awareness: state.awareness,
      user_notes: state.notes.trim() ? state.notes : null,
      time_pressure_flag: state.timePressure,
      transition_flag: state.transition,
      endgame_flag: state.endgame,
    })
  }

  // Keyboard shortcuts per DESIGN.md classification UI.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
        // Esc still works inside textareas — useful to bail without
        // touching the mouse.
        if (e.key === 'Escape') {
          ;(e.target as HTMLElement).blur()
        }
        return
      }
      if (e.key >= '1' && e.key <= '4') {
        e.preventDefault()
        setState((s) => ({ ...s, step: Number.parseInt(e.key, 10) }))
      } else if (e.key === 'g' || e.key === 'G') {
        e.preventDefault()
        setState((s) => ({ ...s, awareness: 'got_it_wrong' }))
      } else if (e.key === 'd' || e.key === 'D') {
        e.preventDefault()
        setState((s) => ({ ...s, awareness: 'didnt_see_it' }))
      } else if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        save()
      } else if (e.key === 'Escape') {
        e.preventDefault()
        onBack()
      } else if (e.key === 'n' || e.key === 'N') {
        e.preventDefault()
        notesRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, mistake.id])

  const canSave = state.step !== null

  return (
    <div className="classify">
      <fieldset className="classify-section">
        <legend>
          <span className="legend-num">1</span>
          <span className="legend-text">What thinking step failed?</span>
          <span className="legend-hint">
            <kbd>1</kbd>
            <kbd>2</kbd>
            <kbd>3</kbd>
            <kbd>4</kbd>
          </span>
        </legend>
        <div className="step-grid">
          {[1, 2, 3, 4].map((n) => {
            const selected = state.step === n
            const isSuggested = showSuggested && mistake.suggested_step === n
            const label = STEP_LABELS[n]
            return (
              <button
                key={n}
                type="button"
                className={
                  'step-card' +
                  (selected ? ' selected' : '') +
                  (isSuggested && !selected ? ' suggested' : '')
                }
                onClick={() => setState((s) => ({ ...s, step: n }))}
              >
                <span className="step-card-num">{n}</span>
                <span className="step-card-body">
                  <span className="step-card-title">{label?.title}</span>
                  <span className="step-card-gloss">{label?.gloss}</span>
                </span>
                {isSuggested && !selected && (
                  <span className="step-card-suggested-tag">Suggested</span>
                )}
              </button>
            )
          })}
        </div>
      </fieldset>

      <fieldset className="classify-section">
        <legend>
          <span className="legend-num">2</span>
          <span className="legend-text">Did you see it?</span>
          <span className="legend-hint">
            <kbd>G</kbd>
            <kbd>D</kbd>
          </span>
        </legend>
        <div className="awareness-row">
          <button
            type="button"
            className={
              'awareness-button' +
              (state.awareness === 'got_it_wrong' ? ' selected' : '')
            }
            onClick={() =>
              setState((s) => ({ ...s, awareness: 'got_it_wrong' }))
            }
          >
            <span className="awareness-key">G</span>
            <span className="awareness-body">
              <span className="awareness-title">Got it wrong</span>
              <span className="awareness-gloss">
                I saw it but evaluated it wrong
              </span>
            </span>
          </button>
          <button
            type="button"
            className={
              'awareness-button' +
              (state.awareness === 'didnt_see_it' ? ' selected' : '')
            }
            onClick={() =>
              setState((s) => ({ ...s, awareness: 'didnt_see_it' }))
            }
          >
            <span className="awareness-key">D</span>
            <span className="awareness-body">
              <span className="awareness-title">Didn’t see it</span>
              <span className="awareness-gloss">It wasn’t in my candidates</span>
            </span>
          </button>
        </div>
      </fieldset>

      <fieldset className="classify-section">
        <legend>
          <span className="legend-num">3</span>
          <span className="legend-text">Tags (auto-flagged)</span>
        </legend>
        <div className="tag-row">
          <ToggleChip
            label="Time pressure"
            on={state.timePressure}
            onChange={(v) => setState((s) => ({ ...s, timePressure: v }))}
          />
          <ToggleChip
            label="Transition"
            on={state.transition}
            onChange={(v) => setState((s) => ({ ...s, transition: v }))}
          />
          <ToggleChip
            label="Endgame"
            on={state.endgame}
            onChange={(v) => setState((s) => ({ ...s, endgame: v }))}
          />
        </div>
      </fieldset>

      <fieldset className="classify-section">
        <legend>
          <span className="legend-num">4</span>
          <span className="legend-text">Notes</span>
          <span className="legend-hint">
            <kbd>N</kbd> to focus
          </span>
        </legend>
        <textarea
          ref={notesRef}
          className="classify-notes"
          value={state.notes}
          onChange={(e) => setState((s) => ({ ...s, notes: e.target.value }))}
          placeholder="What were you thinking when you played this?"
          rows={3}
        />
      </fieldset>

      <div className="classify-actions">
        <button
          type="button"
          className="action-back"
          onClick={onBack}
          disabled={saving}
        >
          <kbd>Esc</kbd> Back
        </button>
        <button type="button" onClick={onSkip} disabled={saving}>
          Skip
        </button>
        <button
          type="button"
          className="action-save"
          onClick={save}
          disabled={!canSave || saving}
          title={canSave ? 'Save and advance' : 'Pick a step first'}
        >
          {saving ? 'Saving…' : (
            <>
              Save &amp; next <kbd>Enter</kbd>
            </>
          )}
        </button>
      </div>
    </div>
  )
}

interface ToggleChipProps {
  label: string
  on: boolean
  onChange: (v: boolean) => void
}

function ToggleChip({ label, on, onChange }: ToggleChipProps) {
  return (
    <button
      type="button"
      className={'chip-toggle' + (on ? ' on' : '')}
      onClick={() => onChange(!on)}
      aria-pressed={on}
    >
      <span className="chip-toggle-mark">{on ? '●' : '○'}</span>
      {label}
    </button>
  )
}
