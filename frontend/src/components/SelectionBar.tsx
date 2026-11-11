import { useState } from 'react'
import type { Item, Status, Summary } from '../types'
import type { TabId } from './Tabs'
import { shownPrice } from '../sort'
import Price from './Price'
import { CloseIcon } from './Icons'

// What a button in the bar asks for: move the ticked items, "park the
// rest" (move every UNticked wish-list item to Later), or delete the ticked ones.
export type BulkAction = { move: Status } | 'park-rest' | 'delete'

// Marking this many or more as bought asks "are you sure?" first: after
// Select all, one stray tap would otherwise move the whole wish list.
const CONFIRM_FROM = 5

interface SelectionBarProps {
  tab: TabId
  picked: Item[]
  allPicked: boolean // every item on this tab is ticked
  summary: Summary
  onAction: (action: BulkAction) => Promise<void>
  onClear: () => void
}

// The "what if?" bar. It appears while something is ticked, adds up the
// ticked prices as you tap, and (on Wish list and Later) says whether they
// fit. Nothing changes until one of its buttons is pressed.
//
// What the total is compared with:
//   Wish list  the budget minus what's already spent this month
//              ("if I bought only these, would I be OK?")
//   Later      the same, minus the wish list too
//              ("can I bring these back on top of my plans?")
//   Bought     nothing: these are already in "spent", so a "left" figure
//              would count them twice. The total is what you paid.
//   All        nothing: a mix of bought and not-yet-bought has no honest
//              "left" figure.
export default function SelectionBar({ tab, picked, allPicked, summary, onAction, onClear }: SelectionBarProps) {
  const [busy, setBusy] = useState(false)
  // The number of items "Mark bought" was armed for. If the ticks change,
  // the number no longer matches and the question quietly goes away.
  const [armedFor, setArmedFor] = useState<number | null>(null)
  // Delete always asks first (there's no undo yet), for the same number of items.
  const [deleteFor, setDeleteFor] = useState<number | null>(null)
  const confirmingDelete = deleteFor != null && deleteFor === picked.length

  const total = picked.reduce((sum, i) => sum + (shownPrice(i) ?? 0), 0)
  const unpriced = picked.filter((i) => shownPrice(i) == null).length
  const toBuy = picked.filter((i) => i.status !== 'purchased').length
  const confirming = armedFor != null && armedFor === toBuy

  const compares = tab === 'planned' || tab === 'later'
  const { budget, spent_this_month: spent, planned_total: planned } = summary
  const room = budget == null ? null : budget - spent - (tab === 'later' ? planned : 0)
  const left = room == null ? null : room - total

  async function run(action: BulkAction) {
    setBusy(true)
    try {
      await onAction(action)
    } finally {
      setBusy(false)
      setArmedFor(null)
      setDeleteFor(null)
    }
  }

  function markBought() {
    if (toBuy >= CONFIRM_FROM && !confirming) setArmedFor(toBuy)
    else run({ move: 'purchased' })
  }

  const markBoughtBtn = (
    <button className="btn btn-primary" disabled={busy} onClick={markBought}>
      Mark bought
    </button>
  )

  return (
    <section className="card select-bar" role="region" aria-label="Selected items" aria-live="polite">
      <div className="select-top">
        <div className="select-sum">
          <span className="eyebrow">{picked.length} selected</span>
          <Price amount={total} className="select-total" />
        </div>
        <div className="select-verdict">
          {!compares ? (
            <span className="budget-note">{tab === 'purchased' ? 'what you paid' : 'together'}</span>
          ) : left == null ? (
            <span className="budget-note">Set a budget to compare</span>
          ) : (
            <>
              <span className={left < 0 ? 'select-left is-over' : 'select-left'}>
                <Price amount={Math.abs(left)} /> {left < 0 ? 'over' : 'left'}
              </span>
              <span className="budget-note">{tab === 'later' ? 'with your wish list' : 'this month'}</span>
            </>
          )}
        </div>
        <button className="icon-btn select-clear" aria-label="Clear selection" onClick={onClear} disabled={busy}>
          <CloseIcon />
        </button>
      </div>
      {unpriced > 0 && (
        <p className="budget-note">{unpriced} without a price {unpriced === 1 ? 'isn’t' : 'aren’t'} counted.</p>
      )}

      {confirmingDelete ? (
        <div className="select-confirm">
          <p>
            Delete {picked.length === 1 ? 'this item' : `${picked.length} items`}? This can’t be undone.
          </p>
          <div className="select-actions">
            <button className="btn btn-secondary" disabled={busy} onClick={() => setDeleteFor(null)}>
              Cancel
            </button>
            <button className="btn btn-danger" disabled={busy} onClick={() => run('delete')}>
              Yes, delete
            </button>
          </div>
        </div>
      ) : confirming ? (
        <div className="select-confirm">
          <p>Mark {toBuy} items as bought? They’ll count as spent this month.</p>
          <div className="select-actions">
            <button className="btn btn-secondary" disabled={busy} onClick={() => setArmedFor(null)}>
              Cancel
            </button>
            <button className="btn btn-primary" disabled={busy} onClick={() => run({ move: 'purchased' })}>
              Yes, mark bought
            </button>
          </div>
        </div>
      ) : (
        <div className="select-actions">
          {tab === 'planned' && (
            <>
              {markBoughtBtn}
              <button className="btn btn-secondary" disabled={busy} onClick={() => run({ move: 'later' })}>
                Move to Later
              </button>
              {/* everything ticked: there's no "rest" left to park */}
              {!allPicked && (
                <button className="btn btn-secondary" disabled={busy} onClick={() => run('park-rest')}>
                  Park the rest
                </button>
              )}
            </>
          )}
          {tab === 'later' && (
            <button className="btn btn-primary" disabled={busy} onClick={() => run({ move: 'planned' })}>
              Back to wish list
            </button>
          )}
          {tab === 'purchased' && (
            <>
              <button className="btn btn-primary" disabled={busy} onClick={() => run({ move: 'planned' })}>
                Back to wish list
              </button>
              <button className="btn btn-secondary" disabled={busy} onClick={() => run({ move: 'later' })}>
                Move to Later
              </button>
            </>
          )}
          {tab === 'all' && (
            <>
              {markBoughtBtn}
              <button className="btn btn-secondary" disabled={busy} onClick={() => run({ move: 'later' })}>
                To Later
              </button>
              <button className="btn btn-secondary" disabled={busy} onClick={() => run({ move: 'planned' })}>
                To wish list
              </button>
            </>
          )}
          {/* on every tab; asks first */}
          <button className="btn btn-quiet select-delete" disabled={busy} onClick={() => setDeleteFor(picked.length)}>
            Delete
          </button>
        </div>
      )}
    </section>
  )
}
