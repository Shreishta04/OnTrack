import { useState, type FormEvent } from 'react'
import type { Item, Status } from '../types'
import { displayName, problemText, shortDate, storeName, stuckTip } from '../format'
import { useMoney } from '../money'
import Price from './Price'
import Thumb from './Thumb'

const TAG = { planned: 'Wish list', later: 'Later', purchased: 'Bought' }

// The note beside the store name: where the item is, or when it was saved.
// (No "fits / over budget" here: tick items and the selection bar adds
// them up. "Needs a price" sits on the right, where the price would be.)
function badgeFor(item: Item): { text: string; tone: 'good' | 'warn' | 'muted' } | null {
  if (item.status === 'later') return { text: 'Parked', tone: 'muted' }
  if (item.status === 'purchased') return { text: `Bought ${shortDate(item.purchased_at)}`, tone: 'muted' }
  return null
}

// The fields Edit (and "type a price") can change.
export interface ItemEdit {
  name?: string
  note?: string | null
  manual_price?: number | null // your own price, used while no store gives one
  purchased_price?: number // what you paid (Bought only)
}

// What a button in a row can ask for: move to a list, delete, or save edits.
export type RowAction = Status | 'delete' | { edit: ItemEdit }

interface ItemRowProps {
  item: Item
  showTag: boolean
  onAction: (item: Item, action: RowAction) => Promise<void>
  picked?: boolean // undefined: no tick box on this row
  onPick?: () => void
}

export default function ItemRow({ item, showTag, onAction, picked, onPick }: ItemRowProps) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)               // a request is in progress
  const [confirmDelete, setConfirmDelete] = useState(false) // first tap on Delete
  const [editing, setEditing] = useState(false)

  async function run(action: RowAction) {
    setBusy(true)
    await onAction(item, action)
    setBusy(false)
  }

  function handleDelete() {
    if (!confirmDelete) {
      // First tap only arms the button; it calms down again after 3 seconds.
      setConfirmDelete(true)
      setTimeout(() => setConfirmDelete(false), 3000)
      return
    }
    run('delete')
  }

  const bought = item.status === 'purchased'
  const shownPrice = bought ? item.purchased_price : item.price
  const showMrp = !bought && item.mrp != null && item.price != null && item.mrp > item.price
  const badge = badgeFor(item)
  const reason = item.needs_price ? problemText(item) : null
  const typed = item.best_link_id == null && item.manual_price != null // price came from you, not a store
  const link = item.links.find((l) => l.id === item.best_link_id) ?? item.links[0]
  const drop =
    !bought && link?.price_when_saved != null && item.price != null && link.price_when_saved > item.price
      ? link.price_when_saved - item.price
      : 0
  const name = displayName(item)

  return (
    <div className={`row${open ? ' open' : ''}${picked ? ' is-picked' : ''}`}>
      <div className="row-line">
      {picked !== undefined && (
        <button
          className={picked ? 'pick is-on' : 'pick'}
          role="checkbox"
          aria-checked={picked}
          aria-label={`Select ${name}`}
          onClick={onPick}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M5 12.5l4.5 4.5L19 7.5" />
          </svg>
        </button>
      )}
      <button className="row-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        {/* An item still named after its URL would show "H" (from https), so use the store's letter */}
        <Thumb src={item.image} name={name} />

        <div className="row-text">
          <div className="row-name">{name}</div>
          <div className="row-meta">
            <span>{storeName(item)}</span>
            {badge ? (
              <>
                <span aria-hidden="true">·</span>
                <span className={`badge badge-${badge.tone}`}>
                  <i className="badge-dot" />
                  {badge.text}
                </span>
              </>
            ) : (
              <>
                <span aria-hidden="true">·</span>
                <span>{shortDate(item.created_at)}</span>
              </>
            )}
            {showTag && <span className="tag">{TAG[item.status]}</span>}
          </div>
        </div>

        {/* Under the price: how much it has dropped (green pill), else the
            struck-through MRP. No price yet: a clay pill instead. */}
        <div className="row-price">
          {item.needs_price && shownPrice == null ? (
            <span className="pill pill-warn">Needs a price</span>
          ) : (
            <>
              <Price amount={shownPrice} className="row-amount" />
              {drop > 0 ? (
                <span className="pill pill-good">↓ <Price amount={drop} /></span>
              ) : (
                showMrp && <Price amount={item.mrp} className="row-mrp" />
              )}
            </>
          )}
        </div>
      </button>
      </div>

      {open && (
        <div className="row-details">
          {bought ? (
            <p>
              Paid <Price amount={item.purchased_price} /> on {shortDate(item.purchased_at)} · saved to your list{' '}
              {shortDate(item.created_at)}
            </p>
                    ) : item.needs_price ? (
            <>
              {reason && <p className="row-reason">{reason}</p>}
              <p>{stuckTip(item)}</p>
              {!editing && <PriceBox item={item} onSave={(price) => run({ edit: { manual_price: price } })} />}
            </>
          ) : typed ? (
            <p>
              {item.links.length > 0 && <>{storeName(item)} · </>}
              <Price amount={item.price} /> <span className="typed">typed by you</span> · saved{' '}
              {shortDate(item.created_at)}
            </p>
          ) : (
            <p>
              {storeName(item)} · <Price amount={item.price} /> now
              {link?.lowest_price_seen != null && (
                <>
                  {' '}· lowest seen <Price amount={link.lowest_price_seen} />
                </>
              )}{' '}
              · saved {shortDate(item.created_at)}
            </p>
          )}
          {item.note && !editing && <p className="row-note">{item.note}</p>}
          {drop > 0 && (
            <p className="drop">
              ↓ <Price amount={drop} /> since you saved it
            </p>
          )}
          {link && (
            <a className="row-link" href={link.url} target="_blank" rel="noreferrer">
              Open in {storeName(item)} ↗
            </a>
          )}

          {editing ? (
            <EditForm
              item={item}
              onCancel={() => setEditing(false)}
              onSave={async (edit) => {
                await run({ edit })
                setEditing(false)
              }}
            />
          ) : (
          <div className="row-actions">
            {item.status === 'planned' && (
              <>
                <button className="btn btn-primary" disabled={busy} onClick={() => run('purchased')}>
                  Mark bought
                </button>
                <button className="btn btn-secondary" disabled={busy} onClick={() => run('later')}>
                  Move to Later
                </button>
              </>
            )}
            {item.status === 'later' && (
              <>
                <button className="btn btn-primary" disabled={busy} onClick={() => run('planned')}>
                  Back to wish list
                </button>
                <button className="btn btn-secondary" disabled={busy} onClick={() => run('purchased')}>
                  Mark bought
                </button>
              </>
            )}
            {item.status === 'purchased' && (
              <button className="btn btn-secondary" disabled={busy} onClick={() => run('planned')}>
                Undo purchase
              </button>
            )}
            <button className="btn btn-quiet" disabled={busy} onClick={() => setEditing(true)}>
              Edit
            </button>
            <button
              className={confirmDelete ? 'btn btn-quiet is-armed' : 'btn btn-quiet'}
              disabled={busy}
              onClick={handleDelete}
            >
              {confirmDelete ? 'Tap again to delete' : 'Delete'}
            </button>
          </div>
          )}
        </div>
      )}
    </div>
  )
}

// "Needs a price": type it here instead of deleting the item and adding it
// again by hand. The store's link stays, so a later refresh can still find
// the store's own price (which then counts instead of yours).
function PriceBox({ item, onSave }: { item: Item; onSave: (price: number) => Promise<void> }) {
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const money = useMoney()

  async function submit(e: FormEvent) {
    e.preventDefault()
    const price = Number(draft)
    if (draft.trim() === '' || !Number.isFinite(price) || price < 0) return
    setSaving(true)
    await onSave(price)
    setSaving(false)
  }

  return (
    <form className="price-box" onSubmit={submit}>
      <label className="sr-only" htmlFor={`price-${item.id}`}>Price of {displayName(item)}</label>
      <span className="price-box-symbol" aria-hidden="true">{money.symbol}</span>
      <input
        id={`price-${item.id}`}
        className="field price-box-input"
        type="number"
        min="0"
        step="any"
        inputMode="decimal"
        placeholder="Type the price"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
      <button className="btn btn-primary" type="submit" disabled={saving || draft.trim() === ''}>
        {saving ? 'Saving…' : 'Save'}
      </button>
    </form>
  )
}

// Edit: the name, a note, and a price. Which price depends on the item:
//   bought                  what you paid
//   a store gives a price   nothing to type (the store's price counts)
//   otherwise               your own price
function EditForm({ item, onSave, onCancel }: {
  item: Item
  onSave: (edit: ItemEdit) => Promise<void>
  onCancel: () => void
}) {
  const bought = item.status === 'purchased'
  const storePrice = item.best_link_id != null
  const startPrice = bought ? item.purchased_price : storePrice ? null : item.manual_price
  const [name, setName] = useState(displayName(item))
  const [note, setNote] = useState(item.note ?? '')
  const [price, setPrice] = useState(startPrice == null ? '' : String(startPrice))
  const [saving, setSaving] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const money = useMoney()
  const id = `edit-${item.id}`

  async function submit(e: FormEvent) {
    e.preventDefault()
    const edit: ItemEdit = {}
    const cleanName = name.trim()
    if (!cleanName) return setProblem('Give it a name.')
    if (cleanName !== displayName(item)) edit.name = cleanName
    if (note.trim() !== (item.note ?? '')) edit.note = note.trim() || null
    if (bought || !storePrice) {
      const n = price.trim() === '' ? null : Number(price)
      if (n != null && (!Number.isFinite(n) || n < 0)) return setProblem('The price should be a number, like 1299.')
      if (bought && n != null && n !== item.purchased_price) edit.purchased_price = n
      if (!bought && n !== item.manual_price) edit.manual_price = n
    }
    if (Object.keys(edit).length === 0) return onCancel()
    setSaving(true)
    setProblem(null)
    await onSave(edit)
    setSaving(false)
  }

  return (
    <form className="edit-form" onSubmit={submit}>
      <label className="eyebrow" htmlFor={`${id}-name`}>Name</label>
      <input id={`${id}-name`} className="field" value={name} maxLength={300} onChange={(e) => setName(e.target.value)} />

      {bought || !storePrice ? (
        <>
          <label className="eyebrow" htmlFor={`${id}-price`}>
            {bought ? `Price you paid (${money.symbol})` : `Your price (${money.symbol})`}
          </label>
          <input id={`${id}-price`} className="field" type="number" min="0" step="any" inputMode="decimal"
            placeholder={bought ? '' : 'Until a store gives one'} value={price} onChange={(e) => setPrice(e.target.value)} />
        </>
      ) : (
        <p className="budget-note">
          The price comes from {storeName(item)} (<Price amount={item.price} />) and updates on refresh.
        </p>
      )}

      <label className="eyebrow" htmlFor={`${id}-note`}>Note</label>
      <textarea id={`${id}-note`} className="field edit-note" rows={2} maxLength={1000}
        placeholder="Size, colour, for whom…" value={note} onChange={(e) => setNote(e.target.value)} />

      {problem && <p className="notice notice-error">{problem}</p>}
      <div className="row-actions">
        <button className="btn btn-primary" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
        <button className="btn btn-secondary" type="button" disabled={saving} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}
