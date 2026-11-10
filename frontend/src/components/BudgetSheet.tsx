import { useEffect } from 'react'
import BudgetEditor from './BudgetEditor'
import { CloseIcon } from './Icons'

interface BudgetSheetProps {
  current: number | null
  onClose: () => void
  onSaved: () => Promise<void>
}

// Tapping the budget card opens this small sheet from the bottom: a shortcut
// to the same editor that's in Settings → Budget.
export default function BudgetSheet({ current, onClose, onSaved }: BudgetSheetProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="sheet-layer">
      <button className="scrim" aria-label="Close" onClick={onClose} />
      <section className="card sheet" role="dialog" aria-modal="true" aria-labelledby="budget-title">
        <div className="sheet-head">
          <h2 id="budget-title" className="sheet-title">Your budget</h2>
          <button className="icon-btn" aria-label="Close" onClick={onClose}>
            <CloseIcon />
          </button>
        </div>
        <div className="sheet-body">
          <BudgetEditor current={current} onCancel={onClose} onSaved={onSaved} />
        </div>
      </section>
    </div>
  )
}
