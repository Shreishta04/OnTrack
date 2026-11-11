// Small helpers for turning raw data into friendly text.

import type { Item, RefreshResult } from './types'

// Stores whose web address doesn't spell their name nicely.
const STORE_NAMES: [RegExp, string][] = [
  [/amazon|amzn/, 'Amazon'],
  [/victoriassecret/, 'Victoria’s Secret'],
  [/littlebox/, 'Littlebox'],
  [/savana/, 'Savana'],
  [/tiktok/, 'TikTok'],
  [/tirabeauty/, 'Tira'],
  [/nykaa/, 'Nykaa'],
  [/(^|\.)hm\.com/, 'H&M'],
  [/ajio/, 'AJIO'],
  [/shein/, 'SHEIN'],
  [/bathandbodyworks/, 'Bath & Body Works'],
]

// "https://www.amazon.in/dp/…" → "Amazon"; "coach.in" → "Coach"
export function storeName(item: Item): string {
  const url = item.links[0]?.url
  if (!url) return 'Added by hand'
  let host: string
  try {
    host = new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return 'Link'
  }
  const known = STORE_NAMES.find(([pattern]) => pattern.test(host))
  if (known) return known[1]
  const base = host.split('.')[0]
  return base.charAt(0).toUpperCase() + base.slice(1)
}

// An item saved while the store showed nothing is named after its link
// until a check finds the real name. Show "Amazon item" instead of
// "https://www.amazon.com/dp/B0…". (The server keeps the link as the name,
// because that's how it knows to rename it later.)
export function displayName(item: Item): string {
  return item.name.startsWith('http') ? `${storeName(item)} item` : item.name
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
  return 'Type the price below, or OnTrack tries again on the next refresh.'
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

// Calendar days ("2026-11-25"), worked out without time zones getting in the
// way: they're already on the person's own calendar.
export function dayMonth(day: string): string {
  const [y, m, d] = day.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', timeZone: 'UTC' })
}

export function addDays(day: string, n: number): string {
  const [y, m, d] = day.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10)
}

// 1 → "1st", 22 → "22nd", 13 → "13th"
export function ordinal(n: number): string {
  const tens = n % 100
  const suffix = tens >= 11 && tens <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th'
  return `${n}${suffix}`
}

// The same reset rule as the server (services.next_reset_after): the first
// reset date after `day`; the 29th–31st become a short month's last day.
export function nextResetAfter(day: string, resetDay: number): string {
  const [y, m] = day.split('-').map(Number)
  const clamp = (year: number, month: number) => {
    const last = new Date(Date.UTC(year, month + 1, 0)).getUTCDate() // month is 0-based here
    return new Date(Date.UTC(year, month, Math.min(resetDay, last))).toISOString().slice(0, 10)
  }
  const thisMonth = clamp(y, m - 1)
  if (thisMonth > day) return thisMonth
  return m === 12 ? clamp(y + 1, 0) : clamp(y, m)
}

// "2026-10-05T11:56:46+00:00" → "5 Oct"
export function shortDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}
