import { useState, type FormEvent } from 'react'
import { setBudget } from '../api'
import type { Summary } from '../types'
import Price from './Price'

interface BudgetCardProps {
  summary: Summary
  onBudgetSaved: () => Promise<void>
}

export default function BudgetCard({ summary, onBudgetSaved }: BudgetCardProps) {
  const { budget, spent_this_month: spent, planned_total: planned, remaining } = summary
  const [editing, setEditing] = useState(false)

  const editor = editing ? (
    <BudgetEditor
      current={budget}
      onCancel={() => setEditing(false)}
      onSaved={async () => {
        await onBudgetSaved()
        setEditing(false)
      }}
    />
  ) : (
    <button className="btn btn-secondary budget-btn" onClick={() => setEditing(true)}>
      {budget == null ? 'Set a budget' : 'Edit budget'}
    </button>
  )

  // No budget set yet: nothing to measure against.
  if (budget == null || remaining == null) {
    return (
      <section className="card budget-card" aria-label="Budget summary">
        <div className="eyebrow">No budget yet</div>
        <p className="budget-note">Set a monthly budget to see what's left after your wish list.</p>
        <Stats spent={spent} planned={planned} budget={null} />
        {editor}
      </section>
    )
  }

  const over = remaining < 0
  const percent = (n: number) => (budget > 0 ? Math.min(100, Math.max(0, (n / budget) * 100)) : 0)
  const spentPct = percent(spent)
  const plannedPct = Math.min(100 - spentPct, percent(planned))

  return (
    <section className="card budget-card" aria-label="Budget summary">
      <div className="budget-hero">
        <div className="eyebrow">{over ? 'Over budget' : 'Left after wish list'}</div>
        <Price amount={Math.abs(remaining)} className={over ? 'hero-amount is-over' : 'hero-amount'} />
      </div>

      <div className="bar" aria-hidden="true">
        <div className="bar-seg bar-spent" style={{ width: `${spentPct}%` }} />
        <div className="bar-seg bar-planned" style={{ width: `${plannedPct}%` }} />
      </div>

      <Stats spent={spent} planned={planned} budget={budget} />

      {editor}
    </section>
  )
}

// The small form that appears inside the card when you tap "Edit budget".
function BudgetEditor({
  current,
  onCancel,
  onSaved,
}: {
  current: number | null
  onCancel: () => void
  onSaved: () => Promise<void>
}) {
  const [draft, setDraft] = useState(current == null ? '' : String(current))
  const [saving, setSaving] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

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
      <label className="eyebrow" htmlFor="budget-input">Monthly budget (₹)</label>
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

// The three small numbers under the bar. A separate component because
// both versions of the card above use it.
function Stats({ spent, planned, budget }: { spent: number; planned: number; budget: number | null }) {
  return (
    <div className="stats">
      <div className="stat">
        <span className="eyebrow"><i className="dot dot-spent" />Spent</span>
        <Price amount={spent} className="stat-amount" />
      </div>
      <div className="stat">
        <span className="eyebrow"><i className="dot dot-planned" />Planned</span>
        <Price amount={planned} className="stat-amount" />
      </div>
      <div className="stat">
        <span className="eyebrow"><i className="dot dot-budget" />Budget</span>
        <Price amount={budget} className="stat-amount" />
      </div>
    </div>
  )
}
