import { useState } from 'react'
import type { Item, Status } from '../types'
import { problemText, shortDate, storeName, stuckTip } from '../format'
import Price from './Price'
import Thumb from './Thumb'

const TAG = { planned: 'Wish list', later: 'Later', purchased: 'Bought' }

// The coloured note beside the store name.
function badgeFor(item: Item): { text: string; tone: 'good' | 'warn' | 'muted' } | null {
  if (item.status === 'later') return { text: 'Parked', tone: 'muted' }
  if (item.status === 'purchased') return { text: `Bought ${shortDate(item.purchased_at)}`, tone: 'muted' }
  if (item.needs_price) return { text: 'Needs a price', tone: 'warn' }
  if (item.fits_budget === true) return { text: 'Fits budget', tone: 'good' }
  if (item.fits_budget === false) return { text: 'Over budget', tone: 'warn' }
  return null // no budget set yet
}

// What a button in a row can ask for: move to a list, or delete.
export type RowAction = Status | 'delete'

interface ItemRowProps {
  item: Item
  showTag: boolean
  onAction: (item: Item, action: RowAction) => Promise<void>
}

export default function ItemRow({ item, showTag, onAction }: ItemRowProps) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)               // a request is in progress
  const [confirmDelete, setConfirmDelete] = useState(false) // first tap on Delete

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

  return (
    <div className={open ? 'row open' : 'row'}>
      <button className="row-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        {/* An item still named after its URL would show "H" (from https), so use the store's letter */}
        <Thumb src={item.image} name={item.name.startsWith('http') ? storeName(item) : item.name} />

        <div className="row-text">
          <div className="row-name">{item.name}</div>
          <div className="row-meta">
            <span>{storeName(item)}</span>
            {badge && (
              <>
                <span aria-hidden="true">·</span>
                <span className={`badge badge-${badge.tone}`}>
                  <i className="badge-dot" />
                  {badge.text}
                </span>
              </>
            )}
            {showTag && <span className="tag">{TAG[item.status]}</span>}
          </div>
        </div>

        <div className="row-price">
          <Price amount={shownPrice} className="row-amount" />
          {showMrp && <Price amount={item.mrp} className="row-mrp" />}
        </div>

        <svg className="plus" width="20" height="20" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
          <path d="M12 5v14M5 12h14" />
        </svg>
      </button>

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
            <button
              className={confirmDelete ? 'btn btn-quiet is-armed' : 'btn btn-quiet'}
              disabled={busy}
              onClick={handleDelete}
            >
              {confirmDelete ? 'Tap again to delete' : 'Delete'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
