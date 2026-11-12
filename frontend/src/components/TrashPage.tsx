import { useEffect, useState, type ReactNode } from 'react'
import { emptyTrash, getTrash, restoreItem } from '../api'
import type { TrashItem } from '../types'
import { useEdgeBack } from '../hooks/useEdgeBack'
import { displayName, shortDate, storeName } from '../format'
import Price from './Price'
import Thumb from './Thumb'
import { BackIcon } from './Icons'
import { friendly } from '../report'

interface TrashPageProps {
  notes: ReactNode // offline / new version lines, as on the list
  onBack: () => void
  onChanged: () => Promise<void> // something was restored: reload the list
}

const LIST_NAMES = { planned: 'your wish list', later: 'Later', purchased: 'Bought' } as const

// /trash: "Recently deleted". Deleted items wait here for 30 days, then the
// server deletes them for good. Restore puts one back on the list it came
// from, with its prices and price history.
export default function TrashPage({ notes, onBack, onChanged }: TrashPageProps) {
  const [items, setItems] = useState<TrashItem[] | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState<number | 'empty' | null>(null)
  const [armed, setArmed] = useState(false) // "Empty now" tapped once
  const edgeBack = useEdgeBack(onBack)

  useEffect(() => {
    getTrash()
      .then(setItems)
      .catch((e: Error) => setProblem(friendly('Recently deleted', e)))
  }, [])

  async function restore(item: TrashItem) {
    setBusy(item.id)
    setMsg(null)
    try {
      await restoreItem(item.id)
      setItems((now) => now?.filter((i) => i.id !== item.id) ?? null)
      setMsg(`“${displayName(item)}” is back on ${LIST_NAMES[item.status]}.`)
      await onChanged()
    } catch (e) {
      setProblem(friendly('Recently deleted', e))
    }
    setBusy(null)
  }

  async function empty() {
    if (!armed) {
      setArmed(true)
      return
    }
    setBusy('empty')
    try {
      await emptyTrash()
      setItems([])
      setMsg('Recently deleted is empty.')
    } catch (e) {
      setProblem(friendly('Recently deleted', e))
    }
    setArmed(false)
    setBusy(null)
  }

  return (
    <div className="page settings-page trash-page" {...edgeBack}>
      <div className="settings-top">
        <button className="icon-btn" aria-label="Back to your list" onClick={onBack}>
          <BackIcon />
        </button>
      </div>
      <h1 className="settings-title">Recently deleted</h1>
      {notes}
      <p className="set-note trash-lead">
        Items stay here for 30 days, then they’re deleted for good. They don’t count towards your budget.
      </p>

      {problem && <p className="notice notice-error">{problem}</p>}
      {!items && !problem && <p className="notice">Loading…</p>}
      {items && items.length === 0 && <p className="notice trash-empty">Nothing here. Deleted items show up here for 30 days.</p>}

      {items && items.length > 0 && (
        <div className="set-group trash-list">
          {items.map((item) => (
            <div className="trash-row" key={item.id}>
              <Thumb src={item.image} name={displayName(item)} />
              <div className="trash-text">
                <span className="trash-name">{displayName(item)}</span>
                <span className="set-sub">
                  {storeName(item)}
                  {(item.status === 'purchased' ? item.purchased_price : item.price) != null && (
                    <> · <Price amount={(item.status === 'purchased' ? item.purchased_price : item.price)!} /></>
                  )}
                </span>
                <span className="set-sub">{deletedLine(item)}</span>
              </div>
              <button className="btn btn-secondary btn-row" disabled={busy !== null} onClick={() => restore(item)}>
                {busy === item.id ? 'Restoring…' : 'Restore'}
              </button>
            </div>
          ))}
        </div>
      )}

      {msg && <p className="budget-note add-msg" role="status">{msg}</p>}

      {items && items.length > 0 && (
        <button className={armed ? 'set-logout trash-empty-btn is-armed' : 'set-logout trash-empty-btn'}
          disabled={busy !== null} onClick={empty} onBlur={() => setArmed(false)}>
          {busy === 'empty' ? 'Emptying…' : armed ? `Delete ${items.length} for good? Tap again` : 'Empty now'}
        </button>
      )}
    </div>
  )
}

// "Deleted today · 30 days left", "Deleted 4 Nov · 22 days left", "… · last day"
function deletedLine(item: TrashItem): string {
  const today = new Date()
  const local = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  const days = Math.round((Date.parse(item.gone_on) - Date.parse(local)) / 86_400_000)
  const when = shortDate(item.deleted_at) === shortDate(new Date().toISOString()) ? 'Deleted today' : `Deleted ${shortDate(item.deleted_at)}`
  return `${when} · ${days <= 1 ? 'last day' : `${days} days left`}`
}
