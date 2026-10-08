// Small helpers for turning raw data into friendly text.

import type { Item, RefreshResult } from './types' 

// "https://www.amazon.in/dp/…" → "Amazon"
export function storeName(item: Item): string {
  const url = item.links[0]?.url
  if (!url) return 'Added by hand'
  let host: string
  try {
    host = new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return 'Link'
  }
  if (host.includes('amazon') || host.includes('amzn')) return 'Amazon'
  if (host.includes('littlebox')) return 'Littlebox'
  if (host.includes('savana')) return 'Savana'
  const base = host.split('.')[0]
  return base.charAt(0).toUpperCase() + base.slice(1)
}

export function isAmazon(url: string | undefined): boolean {
  return !!url && /amazon\.|amzn\./.test(url)
}

// Why an item has no price, in plain words (null if nothing went wrong).
// Raw errors like "Network error: Timeout: Failed to perform, curl: (28)…"
// are turned into a sentence; our own messages are already readable.
export function problemText(item: Item): string | null {
  const error = item.links.find((l) => l.last_error)?.last_error
  if (!error) return null
  if (error.startsWith('Network error')) {
    return /time(d)? ?out/i.test(error) ? 'The store took too long to answer.' : "Couldn't reach the store."
  }
  const http = error.match(/HTTP (\d+)/)
  if (http) return `The store refused to show the page (error ${http[1]}).`
  return error
}

// What you can do about an item with no price.
export function stuckTip(item: Item): string {
  if (isAmazon(item.links[0]?.url)) {
    return 'Tap Refresh OnTrack on your iPhone, or share this product from there: the name, photo and price fill in by themselves.'
  }
  return 'OnTrack will try again on the next refresh. Or delete it and use Add by hand with your own price.'
}

// The short note after tapping refresh, e.g. "Checked 4 · 1 price dropped".
export function refreshNote(r: RefreshResult): string {
  const parts: string[] = []
  if (r.checked > 0) parts.push(`Checked ${r.checked}`)
  else if (r.skipped_recent > 0) parts.push('All prices were checked in the last hour')

  const dropped = r.changed.filter((c) => c.new_price < c.old_price).length
  const rose = r.changed.length - dropped
  if (dropped) parts.push(`${dropped} ${dropped === 1 ? 'price' : 'prices'} dropped`)
  if (rose) parts.push(`${rose} went up`)
  if (r.failed.length) parts.push(`${r.failed.length} couldn't be read`)
  if (r.phone_only > 0) parts.push('Amazon refreshes from your iPhone')

  return parts.join(' · ') || 'Nothing to refresh yet'
}

// "2026-10-05T11:56:46+00:00" → "5 Oct"
export function shortDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}
