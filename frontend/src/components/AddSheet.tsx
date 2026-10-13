import { useEffect } from 'react'
import type { Item } from '../types'
import AddLink from './AddLink'
import AddByHand from './AddByHand'
import { CloseIcon } from './Icons'

interface AddSheetProps {
  onClose: () => void
  onAdded: (item: Item) => Promise<void>
}

// On the phone, the two add forms live here, behind the + button, so the
// list comes straight after the budget card. Same forms as on the laptop.
export default function AddSheet({ onClose, onAdded }: AddSheetProps) {
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
      <section className="card sheet add-sheet" role="dialog" aria-modal="true" aria-labelledby="add-title">
        <div className="sheet-head">
          <h2 id="add-title" className="serif sheet-title">Add something</h2>
          <button className="icon-btn" aria-label="Close" onClick={onClose}>
            <CloseIcon />
          </button>
        </div>
        <div className="sheet-body">
          <AddLink onAdded={onAdded} label="From a link" />
          <AddByHand onAdded={onAdded} />
        </div>
      </section>
    </div>
  )
}
