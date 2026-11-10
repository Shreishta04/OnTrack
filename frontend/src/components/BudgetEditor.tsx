import { useState, type FormEvent } from 'react'
import { setBudget } from '../api'
import { useMoney } from '../money'

interface BudgetEditorProps {
  current: number | null
  onCancel: () => void
  onSaved: () => Promise<void>
}

// The "how much can I spend this month?" form. Used in two places: the sheet
// that opens when you tap the budget card, and the Budget row in Settings.
export default function BudgetEditor({ current, onCancel, onSaved }: BudgetEditorProps) {
  const [draft, setDraft] = useState(current == null ? '' : String(current))
  const [saving, setSaving] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const money = useMoney()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault() // stop the browser reloading the page, which forms do by default
    const amount = Number(draft)
    if (draft.trim() === '' || !Number.isFinite(amount) || amount < 0) {
      setProblem('Enter an amount, like 15000.')
      return
    }
    setSaving(true)
    setProblem(null)
    try {
      await setBudget(amount)
      await onSaved()
    } catch (err) {
      setProblem((err as Error).message)
      setSaving(false)
    }
  }

  return (
    <form className="budget-edit" onSubmit={handleSubmit}>
      <label className="eyebrow" htmlFor="budget-input">Monthly budget ({money.symbol})</label>
      <input
        id="budget-input"
        className="field"
        type="number"
        min="0"
        inputMode="numeric"
        placeholder="15000"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        autoFocus
      />
      {problem && <p className="notice notice-error">{problem}</p>}
      <div className="budget-edit-actions">
        <button className="btn btn-primary" type="submit" disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button className="btn btn-quiet" type="button" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </form>
  )
}
