import { useEffect } from 'react'

export interface Undo {
  id: number // a new action gets a new id, which restarts the timer
  text: string // "Deleted “Kurta”", "Moved 3 items to Later"
  run: () => Promise<unknown> // puts things back
}

const UNDO_MS = 6000

// The bar at the bottom after Delete, a move or Mark bought: what just
// happened, and Undo. It goes by itself after 6 seconds (the thin line under
// it counts down) or when a newer action replaces it.
export default function UndoBar({ undo, roomForFab, onUndo, onGone }: {
  undo: Undo
  roomForFab: boolean // the phone's + button sits bottom right: keep clear of it
  onUndo: (undo: Undo) => void
  onGone: () => void
}) {
  useEffect(() => {
    const timer = setTimeout(onGone, UNDO_MS)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restart only for a new action
  }, [undo.id])

  return (
    <div className={roomForFab ? 'undo-bar has-fab' : 'undo-bar'} role="status" key={undo.id}>
      <span className="undo-text">{undo.text}</span>
      <button className="undo-btn" onClick={() => onUndo(undo)}>Undo</button>
      <span className="undo-timer" style={{ animationDuration: `${UNDO_MS}ms` }} aria-hidden="true" />
    </div>
  )
}
