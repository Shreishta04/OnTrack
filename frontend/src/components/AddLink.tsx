import { useState, type FormEvent } from 'react'
import { addFromLink } from '../api'
import type { Item } from '../types'

interface AddLinkProps {
  onAdded: (item: Item) => Promise<void>
}

export default function AddLink({ onAdded }: AddLinkProps) {
  const [url, setUrl] = useState('')
  const [adding, setAdding] = useState(false)
  const [message, setMessage] = useState<{ text: string; tone: 'muted' | 'warn' } | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault() // stop the browser reloading the page, which forms do by default
    const link = url.trim()
    if (!link) return
    setAdding(true)
    setMessage(null)
    try {
      const item = await addFromLink(link)
      setUrl('')
      setMessage(
        item.needs_price
          ? { text: `Added “${item.name}”, but couldn't read its price.`, tone: 'warn' }
          : { text: `Added “${item.name}”.`, tone: 'muted' },
      )
      await onAdded(item)
    } catch (err) {
      setMessage({ text: (err as Error).message, tone: 'warn' })
    } finally {
      setAdding(false)
    }
  }

  return (
    <section className="card add-card" aria-label="Add an item">
      <label className="eyebrow" htmlFor="add-link">Add something</label>
      <form className="add-form" onSubmit={handleSubmit}>
        <input
          id="add-link"
          className="field add-input"
          type="url"
          required
          placeholder="Paste a product link"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={adding}
        />
        <button className="btn btn-primary add-btn" type="submit" disabled={adding}>
          {adding ? 'Adding…' : 'Add'}
        </button>
      </form>
      {message ? (
        <p className={message.tone === 'warn' ? 'budget-note add-msg is-warn' : 'budget-note add-msg'} role="status">
          {message.text}
        </p>
      ) : (
        <p className="budget-note">Or share from any app with the “Add to OnTrack” Shortcut.</p>
      )}
    </section>
  )
}