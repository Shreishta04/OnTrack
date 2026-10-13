import { useState } from 'react'
import type { Item, Status, Summary } from '../types'
import Price from './Price'
import { CloseIcon } from './Icons'

// What a button in the bar asks for: move the ticked items, or "park the
// rest" (move every UNticked wish-list item to Later).
export type BulkAction = { move: Status } | 'park-rest'

interface SelectionBarProps {
  tab: 'planned' | 'later'
  picked: Item[]
  summary: Summary
  onAction: (action: BulkAction) => Promise<void>
  onClear: () => void
}

// The "what if I bought just these?" bar. It appears only while something is
// ticked, adds up the ticked prices as you tap, and says whether they fit.
// Nothing changes until one of its buttons is pressed.
//
// What they're compared with:
//   Wish list  the budget minus what's already spent this month
//              ("if I bought only these, would I be OK?")
//   Later      the same, minus the wish list too
//              ("can I bring these back on top of my plans?")
export default function SelectionBar({ tab, picked, summary, onAction, onClear }: SelectionBarProps) {
  const [busy, setBusy] = useState(false)
  const total = picked.reduce((sum, i) => sum + (i.price ?? 0), 0)
  const unpriced = picked.filter((i) => i.price == null).length
  const { budget, spent_this_month: spent, planned_total: planned } = summary
  const room = budget == null ? null : budget - spent - (tab === 'later' ? planned : 0)
  const left = room == null ? null : room - total

  async function run(action: BulkAction) {
    setBusy(true)
    try {
      await onAction(action)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card select-bar" role="region" aria-label="Selected items" aria-live="polite">
      <div className="select-top">
        <div className="select-sum">
          <span className="eyebrow">{picked.length} selected</span>
          <Price amount={total} className="select-total" />
        </div>
        <div className="select-verdict">
          {left == null ? (
            <span className="budget-note">Set a budget to compare</span>
          ) : (
            <span className={left < 0 ? 'select-left is-over' : 'select-left'}>
              <Price amount={Math.abs(left)} /> {left < 0 ? 'over' : 'left'}
            </span>
          )}
          {left != null && (
            <span className="budget-note">{tab === 'later' ? 'with your wish list' : 'this month'}</span>
          )}
        </div>
        <button className="icon-btn select-clear" aria-label="Clear selection" onClick={onClear} disabled={busy}>
          <CloseIcon />
        </button>
      </div>
      {unpriced > 0 && (
        <p className="budget-note">{unpriced} without a price {unpriced === 1 ? 'isn’t' : 'aren’t'} counted.</p>
      )}
      <div className="select-actions">
        {tab === 'planned' ? (
          <>
            <button className="btn btn-primary" disabled={busy} onClick={() => run({ move: 'purchased' })}>
              Mark bought
            </button>
            <button className="btn btn-secondary" disabled={busy} onClick={() => run({ move: 'later' })}>
              Move to Later
            </button>
            <button className="btn btn-secondary" disabled={busy} onClick={() => run('park-rest')}>
              Park the rest
            </button>
          </>
        ) : (
          <button className="btn btn-primary" disabled={busy} onClick={() => run({ move: 'planned' })}>
            Back to wish list
          </button>
        )}
      </div>
    </section>
  )
}
