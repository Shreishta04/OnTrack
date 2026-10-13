import { useState, type FormEvent } from 'react'
import { addFromLink } from '../api'
import type { Item } from '../types'
import { isAmazon } from '../format'

interface AddLinkProps {
  onAdded: (item: Item) => Promise<void>
  label?: string // "From a link" inside the phone's add sheet, which already says "Add something"
}

export default function AddLink({ onAdded, label = 'Add something' }: AddLinkProps) {
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
        item.needs_price && isAmazon(item.links[0]?.url)
          ? { text: 'Added, but Amazon hid the details. Tap Refresh OnTrack on your iPhone to fill them in.', tone: 'warn' }
          : item.needs_price
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
      <label className="eyebrow" htmlFor="add-link">{label}</label>
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
        <p className="budget-note">{shareHint()}</p>
      )}
    </section>
  )
}

// How else to add things, on this kind of device.
function shareHint(): string {
  if (/Android/.test(navigator.userAgent)) {
    return 'Or share a product from any app to OnTrack (once it’s installed). If a store hides its price, add it by hand.'
  }
  if (/iPhone|iPad|iPod/.test(navigator.userAgent)) {
    return 'Or share from any app with the “Add to OnTrack” Shortcut. For Amazon, sharing from the iPhone works best.'
  }
  return 'Or use the OnTrack browser extension on a product page. For Amazon, the extension or the iPhone works best.'
}
