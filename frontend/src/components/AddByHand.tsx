import { useState, type FormEvent } from 'react'
import { addManual } from '../api'
import type { Item } from '../types'

interface AddByHandProps {
  onAdded: (item: Item) => Promise<void>
}

// For anything a store won't let us read: type the name and price yourself.
// The link is optional; with one, Refresh can later bring in the store's price.
export default function AddByHand({ onAdded }: AddByHandProps) {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [price, setPrice] = useState('')
  const [adding, setAdding] = useState(false)
  const [message, setMessage] = useState<{ text: string; tone: 'muted' | 'warn' } | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault() // stop the browser reloading the page
    const amount = Number(price.replace(/[₹,\s]/g, '')) // accept "1,299" or "₹1299"
    if (!name.trim()) return
    if (!Number.isFinite(amount) || amount <= 0) {
      setMessage({ text: 'Type the price as a number, for example 1299.', tone: 'warn' })
      return
    }
    setAdding(true)
    setMessage(null)
    try {
      const item = await addManual(name.trim(), amount, url.trim() || undefined)
      setName('')
      setUrl('')
      setPrice('')
      setMessage({ text: `Added “${item.name}”.`, tone: 'muted' })
      await onAdded(item)
    } catch (err) {
      setMessage({ text: (err as Error).message, tone: 'warn' })
    } finally {
      setAdding(false)
    }
  }

  return (
    <section className="card add-card" aria-label="Add an item by hand">
      <span className="eyebrow">Add by hand</span>
      <form className="hand-form" onSubmit={handleSubmit}>
        <input
          className="field"
          aria-label="What is it?"
          placeholder="What is it?"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={adding}
        />
        <input
          className="field"
          type="url"
          aria-label="Link (optional)"
          placeholder="Link (optional)"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={adding}
        />
        <div className="hand-row">
          <label className="price-field">
            <span className="cur-in" aria-hidden="true">₹</span>
            <input
              className="field"
              inputMode="decimal"
              aria-label="Price"
              placeholder="Price"
              required
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              disabled={adding}
            />
          </label>
          <button className="btn btn-primary add-btn" type="submit" disabled={adding}>
            {adding ? 'Adding…' : 'Add'}
          </button>
        </div>
      </form>
      {message ? (
        <p className={message.tone === 'warn' ? 'budget-note add-msg is-warn' : 'budget-note add-msg'} role="status">
          {message.text}
        </p>
      ) : (
        <p className="budget-note">With a link, Refresh keeps the price up to date. Without one, your price stays as typed.</p>
      )}
    </section>
  )
}