import { useState, type FormEvent } from 'react'
import { setBudget } from '../api'
import type { PeriodInfo } from '../types'
import { useMoney } from '../money'
import { addDays, dayMonth, nextResetAfter, ordinal } from '../format'

interface BudgetEditorProps {
  period?: PeriodInfo // missing only from an older server: then just the amount
  current?: number | null // the budget, when there's no period info
  onCancel?: () => void // no Cancel button without it (the setup screen has Skip)
  onSaved: () => Promise<void>
  saveLabel?: string
}

const DAYS = Array.from({ length: 31 }, (_, i) => i + 1)

// The budget form: how much, for every period or just this one, and the day
// each period starts (the reset day). Used by the sheet on the budget card,
// by Settings → Budget, and by the setup screen after logging in.
export default function BudgetEditor({ period, current, onCancel, onSaved, saveLabel = 'Save' }: BudgetEditorProps) {
  // Each choice starts with its own amount: "Every period" the default,
  // "Just this period" this period's budget. (Starting "Every period" with a
  // one-off amount would quietly make it the new default on Save.)
  const amountFor = (which: 'every' | 'once') =>
    which === 'once' ? (period?.budget ?? null) : (period ? period.default_budget ?? period.budget : current ?? null)
  const asText = (n: number | null) => (n == null ? '' : String(n))
  const [draft, setDraft] = useState(() => asText(amountFor('every')))
  const [scope, setScope] = useState<'every' | 'once'>('every')

  function pickScope(which: 'every' | 'once') {
    if (which === scope) return
    // only swap the amount if it hasn't been typed over
    if (draft === asText(amountFor(scope))) setDraft(asText(amountFor(which)))
    setScope(which)
  }
  const [day, setDay] = useState<number | null>(period?.reset_day ?? null)
  const [saving, setSaving] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const money = useMoney()

  // "Just this period" only makes sense once there's a default to go back to.
  const canBeOnce = period != null && period.default_budget != null

  async function handleSubmit(e: FormEvent) {
    e.preventDefault() // stop the browser reloading the page, which forms do by default
    const amount = Number(draft)
    if (draft.trim() === '' || !Number.isFinite(amount) || amount < 0) {
      setProblem('Enter an amount, like 15000.')
      return
    }
    if (period && day == null) {
      setProblem('Pick the day your budget starts fresh each month.')
      return
    }
    setSaving(true)
    setProblem(null)
    try {
      await setBudget(amount, canBeOnce ? scope : 'every', day ?? undefined)
      await onSaved()
    } catch (err) {
      setProblem((err as Error).message)
      setSaving(false)
    }
  }

  return (
    <form className="budget-edit" onSubmit={handleSubmit}>
      <label className="eyebrow" htmlFor="budget-input">Budget ({money.symbol})</label>
      <input
        id="budget-input"
        className="field"
        type="number"
        min="0"
        inputMode="numeric"
        placeholder="15000"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />

      {canBeOnce && (
        <>
          <div className="scope" role="radiogroup" aria-label="Which periods">
            <button type="button" role="radio" aria-checked={scope === 'every'}
              className={scope === 'every' ? 'scope-btn is-on' : 'scope-btn'} onClick={() => pickScope('every')}>
              Every period
            </button>
            <button type="button" role="radio" aria-checked={scope === 'once'}
              className={scope === 'once' ? 'scope-btn is-on' : 'scope-btn'} onClick={() => pickScope('once')}>
              Just this period
            </button>
          </div>
          <p className="budget-note">
            {scope === 'every'
              ? 'Your default: every new period starts with this amount.'
              : `Only ${dayMonth(period.starts_on)} – ${dayMonth(period.ends_on)}. The next period goes back to your default.`}
          </p>
        </>
      )}

      {period && (
        <>
          <div className="reset-head">
            <span className="eyebrow">Resets on</span>
            <span className="reset-chosen">{day == null ? 'Pick a day' : `the ${ordinal(day)}`}</span>
          </div>
          <p className="budget-note">
            Pick the day your salary, pocket money or other money usually comes in. Your budget starts fresh that day
            each month.
          </p>
          <div className="day-grid" role="group" aria-label="Reset day">
            {DAYS.map((n) => (
              <button
                key={n}
                type="button"
                className={n === day ? 'day is-on' : 'day'}
                aria-pressed={n === day}
                aria-label={`Resets on the ${ordinal(n)}`}
                onClick={() => setDay(n)}
              >
                {n}
              </button>
            ))}
          </div>
          <p className="budget-note">29th–31st: shorter months use their last day.</p>
          {day != null && <Preview period={period} day={day} />}
        </>
      )}

      {problem && <p className="notice notice-error">{problem}</p>}
      <div className="budget-edit-actions">
        <button className="btn btn-primary btn-wide" type="submit" disabled={saving}>
          {saving ? 'Saving…' : saveLabel}
        </button>
        {onCancel && (
          <button className="btn btn-quiet btn-wide" type="button" onClick={onCancel} disabled={saving}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}

// "This period: 1 Nov – 24 Nov. Then a fresh budget on the 25th of every
// month, from 25 Nov." Worked out with the server's rule: a new reset day
// counts from its next date after today.
function Preview({ period, day }: { period: PeriodInfo; day: number }) {
  const today = addDays(period.ends_on, 1 - period.days_left)
  const end = day === period.reset_day ? period.ends_on : addDays(nextResetAfter(today, day), -1)
  const next = addDays(end, 1)
  return (
    <p className="reset-preview" role="status">
      <b>This period: {dayMonth(period.starts_on)} – {dayMonth(end)}</b>
      <br />
      Then a fresh budget on the {ordinal(day)} of every month, from {dayMonth(next)}.
    </p>
  )
}
