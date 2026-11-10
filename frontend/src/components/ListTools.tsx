import { useEffect, useRef, useState } from 'react'
import { SORTS, type SortId } from '../sort'
import { CheckIcon, ChevronIcon } from './Icons'

interface ListToolsProps {
  allPicked: boolean // every item on this tab is ticked
  onSelectAll: () => void
  onClearAll: () => void
  sort: SortId
  onSort: (sort: SortId) => void
}

// The small row between the tabs and the list: "Select all" on the left,
// the sort menu on the right.
export default function ListTools({ allPicked, onSelectAll, onClearAll, sort, onSort }: ListToolsProps) {
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const current = SORTS.find((s) => s.id === sort) ?? SORTS[0]

  // An open menu closes on a tap anywhere else, or on Escape.
  useEffect(() => {
    if (!open) return
    function onPointer(e: PointerEvent) {
      if (!menuRef.current?.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  function choose(next: SortId) {
    onSort(next)
    setOpen(false)
  }

  return (
    <div className="list-tools">
      <button className="chip" onClick={allPicked ? onClearAll : onSelectAll}>
        {allPicked ? 'Clear all' : 'Select all'}
      </button>

      <div className="sort" ref={menuRef}>
        <button
          className={open ? 'chip is-open' : 'chip'}
          aria-haspopup="menu"
          aria-expanded={open}
          aria-label={`Sort: ${current.label}`}
          onClick={() => setOpen(!open)}
        >
          {current.label}
          <ChevronIcon />
        </button>
        {open && (
          <div className="sort-menu" role="menu" aria-label="Sort by">
            {SORTS.map((s) => (
              <button
                key={s.id}
                className="sort-option"
                role="menuitemradio"
                aria-checked={s.id === sort}
                onClick={() => choose(s.id)}
              >
                {s.label}
                {s.id === sort && <CheckIcon />}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
